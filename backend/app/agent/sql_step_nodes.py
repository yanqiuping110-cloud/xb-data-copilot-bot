"""
分步 SQL 执行与结果组装节点（§11.7.4 扩展 · 多 SQL 路径）。
"""

from __future__ import annotations

import re
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.llm_sql import generate_sql_for_plan_step
from app.agent.nodes import _cfg, _span
from app.agent.result_assembler import (
    assemble_intermediate_results,
    combine_step_sqls,
    format_prior_results_summary,
)
from app.agent.state import AskGraphState
from app.core.context import UserContext, UserRole
from app.meta.repository import MetaRepository
from app.policy.role_policy import (
    PolicyError,
    applies_sch_id_filter,
    build_role_context_header,
    require_school_scope,
    strip_sch_id_for_broad_roles,
)
from app.sql.column_guard import validate_sql_columns
from app.sql.executor import execute_readonly
from app.sql.guard import SqlGuardError, validate_sql
from app.agent.plan_compare import get_sql_execution_steps
from app.system.runtime_config import resolve_sql_max_rows
from config.settings import Settings, get_settings


def route_after_build_agent_context(state: AskGraphState) -> str:
    """Agent 上下文构建后：多步 SQL 或单条 CTE 生成。"""
    if state.get("error_code"):
        return "format_answer"
    sql_steps = get_sql_execution_steps(state.get("plan") or {})
    if get_settings().agent_multi_sql_enabled and len(sql_steps) >= 2:
        return "execute_plan_sql_step"
    return "generate_sql_step"


def route_after_execute_plan_sql_step(state: AskGraphState) -> str:
    """单步 SQL 执行后：继续下一步或进入组装。"""
    if state.get("error_code"):
        return "format_answer"
    sql_steps = get_sql_execution_steps(state.get("plan") or {})
    idx = state.get("sql_exec_step_index") or 0
    if idx < len(sql_steps):
        return "execute_plan_sql_step"
    return "assemble_result"


def route_after_assemble_result(state: AskGraphState) -> str:
    """组装完成后进入语义验证或直接回答。"""
    if state.get("error_code"):
        return "format_answer"
    if get_settings().verify_answer_enabled:
        return "verify_answer"
    return "format_answer"


async def _prepare_final_sql(
    raw_sql: str,
    ctx: UserContext,
    settings: Settings,
    copilot_session,
) -> tuple[str, dict[str, Any], str]:
    """校验 SQL 并准备执行参数（与 validate_sql + apply_policy 一致）。"""
    from app.system.sql_context import resolve_sql_context

    sql_ctx = resolve_sql_context(settings)
    final_sql = validate_sql(
        raw_sql,
        ctx,
        max_rows=resolve_sql_max_rows(settings),
        settings=settings,
        sql_ctx=sql_ctx,
    )
    final_sql = strip_sch_id_for_broad_roles(final_sql, ctx, settings=settings)

    meta_repo = MetaRepository(copilot_session)
    table_names = list(
        dict.fromkeys(
            re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)", final_sql, flags=re.IGNORECASE)
        )
    )
    column_map = await meta_repo.load_active_column_names(table_names)
    validate_sql_columns(final_sql, column_map, sql_ctx=sql_ctx)

    found = re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)", final_sql, flags=re.IGNORECASE)
    tables_used = ",".join(dict.fromkeys(t.lower() for t in found))

    params: dict[str, Any] = {}
    if applies_sch_id_filter(ctx, settings=settings):
        if ":sch_id" not in final_sql.lower() and "sch_id" not in final_sql.lower():
            raise SqlGuardError("MISSING_SCH_ID", "学校账户查询必须包含 sch_id 条件")
        params["sch_id"] = require_school_scope(ctx)

    if not applies_sch_id_filter(ctx, settings=settings):
        final_sql = strip_sch_id_for_broad_roles(final_sql, ctx, settings=settings)
        params.pop("sch_id", None)

    return final_sql, params, tables_used


async def execute_plan_sql_step(state: AskGraphState, config: RunnableConfig) -> dict:
    """按 plan 单步生成 SQL、校验并执行，结果写入 intermediate_results。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    ctx: UserContext = c["ctx"]
    question = state.get("normalized_question") or state.get("question") or ""
    plan = state.get("plan") or {}
    plan_steps = get_sql_execution_steps(plan)
    idx = state.get("sql_exec_step_index") or 0

    if idx >= len(plan_steps):
        return {}

    step = plan_steps[idx]
    step_id = step.get("id") or idx + 1
    goal = step.get("goal") or ""

    context_text = state.get("context_text") or ""
    if context_text and not context_text.startswith("【当前用户角色】"):
        context_text = f"{build_role_context_header(ctx, settings=settings)}\n\n{context_text}"

    prior = list(state.get("intermediate_results") or [])
    prior_summary = format_prior_results_summary(prior)

    raw_sql, token_in, token_out = await generate_sql_for_plan_step(
        settings=settings,
        question=question,
        context_text=context_text,
        step=step,
        prior_results_summary=prior_summary,
        thinking_queue=c.get("thinking_delta_queue"),
    )

    if not raw_sql:
        await _span(
            config,
            "execute_plan_sql_step",
            t0,
            "fail",
            {
                "step_id": step_id,
                "goal": goal,
                "error_code": "LLM_NO_SQL",
            },
        )
        return {
            "status": "fail",
            "error_code": "LLM_NO_SQL",
            "error_message": f"步骤 {step_id} 未能生成 SQL",
            "degrade_level": 3,
            "token_in": (state.get("token_in") or 0) + (token_in or 0),
            "token_out": (state.get("token_out") or 0) + (token_out or 0),
        }

    try:
        final_sql, params, tables_used = await _prepare_final_sql(
            raw_sql,
            ctx,
            settings,
            c["copilot_session"],
        )
    except (SqlGuardError, PolicyError) as exc:
        code = getattr(exc, "code", "SQL_VALIDATE_ERROR")
        message = getattr(exc, "message", str(exc))
        await _span(
            config,
            "execute_plan_sql_step",
            t0,
            "fail",
            {"step_id": step_id, "goal": goal, "error_code": code, "sql_preview": raw_sql},
        )
        return {
            "status": "fail",
            "error_code": code,
            "error_message": f"步骤 {step_id} SQL 校验失败：{message}",
            "degrade_level": 3,
        }

    exec_t0 = time.perf_counter()
    try:
        columns, rows = await execute_readonly(
            final_sql,
            params,
            max_rows=resolve_sql_max_rows(settings),
        )
    except Exception as exc:
        await _span(
            config,
            "execute_plan_sql_step",
            t0,
            "fail",
            {
                "step_id": step_id,
                "goal": goal,
                "error_code": "SQL_EXEC_ERROR",
                "sql_preview": final_sql,
                "sql_params": dict(params),
            },
        )
        return {
            "status": "fail",
            "error_code": "SQL_EXEC_ERROR",
            "error_message": f"步骤 {step_id} SQL 执行失败",
            "validation_error": str(exc),
            "degrade_level": 3,
        }

    exec_ms = int((time.perf_counter() - exec_t0) * 1000)
    total_exec_ms = (state.get("latency_ms_sql_exec") or 0) + exec_ms

    intermediate = {
        "step_id": step_id,
        "goal": goal,
        "sql": final_sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "pivot_hint": step.get("pivot_hint"),
        "aggregation": step.get("aggregation"),
        "tables_used": tables_used,
        "entity_label": step.get("entity_label"),
        "join_key": step.get("join_key"),
    }
    prior.append(intermediate)
    sql_steps_meta = list(state.get("sql_steps") or [])
    sql_steps_meta.append(
        {
            "step_id": step_id,
            "goal": goal,
            "aggregation": step.get("aggregation"),
            "pivot_hint": step.get("pivot_hint"),
            "sql": final_sql,
            "row_count": len(rows),
        }
    )

    await _span(
        config,
        "execute_plan_sql_step",
        t0,
        "success",
        {
            "step_id": step_id,
            "goal": goal,
            "step_index": idx,
            "total_steps": len(plan_steps),
            "row_count": len(rows),
            "columns": columns[:12],
            "sql_preview": final_sql,
            "sql_params": dict(params),
        },
    )

    return {
        "intermediate_results": prior,
        "sql_exec_step_index": idx + 1,
        "sql_steps": sql_steps_meta,
        "latency_ms_sql_exec": total_exec_ms,
        "tables_used": tables_used,
        "token_in": (state.get("token_in") or 0) + (token_in or 0),
        "token_out": (state.get("token_out") or 0) + (token_out or 0),
        "use_agent_path": True,
        "status": "running",
    }


async def assemble_result(state: AskGraphState, config: RunnableConfig) -> dict:
    """将 intermediate_results 按 plan 组装为最终 columns/rows。"""
    t0 = time.perf_counter()
    intermediate = list(state.get("intermediate_results") or [])
    plan = state.get("plan")

    columns, rows, mode = assemble_intermediate_results(intermediate, plan)
    combined_sql = combine_step_sqls(intermediate)

    await _span(
        config,
        "assemble_result",
        t0,
        "success" if rows else "empty",
        {
            "assembly_mode": mode,
            "step_count": len(intermediate),
            "row_count": len(rows),
            "column_count": len(columns),
        },
    )

    if not intermediate:
        return {
            "status": "fail",
            "error_code": "NO_INTERMEDIATE_RESULTS",
            "error_message": "分步查询无结果可组装",
            "degrade_level": 3,
        }

    return {
        "columns": columns,
        "rows": rows,
        "raw_sql": combined_sql,
        "final_sql": combined_sql,
        "assembly_mode": mode,
        "status": "running",
        "value_column": "cnt",
        "answer_template": "根据分步查询结果，共返回 {row_count} 行数据。",
    }
