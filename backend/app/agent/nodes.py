"""
LangGraph 问数节点：L1 匹配、LLM 生成、校验、策略、执行与 correct_sql。
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.llm_sql import generate_sql_from_llm
from app.agent.log_utils import get_node_label, get_status_label
from app.agent.state import AskGraphState
from app.core.log_config import get_logger
from app.core.context import UserContext, UserRole
from app.observability import tracer
from app.observability.trace_log import TraceLogCollector
from app.policy.role_policy import (
    PolicyError,
    applies_sch_id_filter,
    build_role_context_header,
    require_school_scope,
    strip_sch_id_for_broad_roles,
)
from app.sql.executor import execute_readonly
from app.meta.repository import MetaRepository
from app.sql.column_guard import validate_sql_columns
from app.sql.guard import SqlGuardError, validate_sql
from app.sql.whitelist import refresh_allowed_tables
from config.settings import Settings, get_settings

_MAX_QUESTION_LEN = 2000
logger = get_logger("agent")


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


def _append_plan_context(context_text: str, state: AskGraphState) -> str:
    """将 plan_question 产物（规划步骤 + 工具观察）追加进 generate_sql Prompt。"""
    plan = state.get("plan")
    observations = state.get("tool_observations") or []
    if not plan and not observations:
        return context_text

    parts = [context_text, "", "【问句规划 plan_question】"]
    if plan:
        parts.append(f"- complexity: {plan.get('complexity')}")
        parts.append(f"- intent: {plan.get('intent')}")
        for step in plan.get("steps") or []:
            goals = step.get("goal") or ""
            tools = ", ".join(step.get("needs_tool") or [])
            parts.append(f"  步骤 {step.get('id')}: {goals}" + (f"（工具: {tools}）" if tools else ""))
    if observations:
        parts.append("")
        parts.append("【Agent 工具观察】")
        for obs in observations[:6]:
            tool = obs.get("tool")
            result = obs.get("result") or {}
            preview = result.get("error") or f"count={result.get('count', result.get('column_count', 'ok'))}"
            parts.append(f"- {tool}: {preview}")
    return "\n".join(parts)


async def _span(
    config: RunnableConfig,
    node_name: str,
    t0: float,
    status: str,
    detail: dict | None = None,
) -> None:
    c = _cfg(config)
    session = c["copilot_session"]
    duration_ms = int((time.perf_counter() - t0) * 1000)
    trace_id = c.get("trace_id", "-")
    await tracer.insert_span(
        session,
        trace_id=trace_id,
        node_name=node_name,
        started_at=datetime.now(),
        duration_ms=duration_ms,
        status=status,
        detail=detail,
    )
    collector: TraceLogCollector | None = c.get("trace_log_collector")
    if collector is not None:
        collector.append_node(
            node_name,
            get_node_label(node_name),
            status,
            duration_ms,
            detail,
        )
    log_fn = logger.warning if status in ("fail", "empty", "degraded") else logger.info
    log_fn(
        "[trace=%s] %s[%s] status=%s[%s] duration_ms=%s detail=%s",
        trace_id,
        get_node_label(node_name),
        node_name,
        get_status_label(status),
        status,
        duration_ms,
        detail,
    )


async def normalize_question(state: AskGraphState, config: RunnableConfig) -> dict:
    """清洗问句、截断长度。"""
    t0 = time.perf_counter()
    q = (state.get("question") or "").strip()
    normalized = q[:_MAX_QUESTION_LEN]
    await _span(config, "normalize_question", t0, "success", {"length": len(normalized)})
    return {"normalized_question": normalized, "status": "running"}


async def generate_sql(state: AskGraphState, config: RunnableConfig) -> dict:
    """LLM 生成 SQL（L0）；失败可 L2 重试一次。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    ctx: UserContext = c["ctx"]
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    context_text = state.get("context_text") or ""
    if context_text and not context_text.startswith("【当前用户角色】"):
        context_text = f"{build_role_context_header(ctx, settings=settings)}\n\n{context_text}"
    context_text = _append_plan_context(context_text, state)
    retry_count = state.get("retry_count") or 0
    l2_retry = False

    sql, token_in, token_out = await generate_sql_from_llm(
        settings=settings,
        question=question,
        context_text=context_text,
        compact=False,
    )
    gen_ms = int((time.perf_counter() - t0) * 1000)

    if not sql and retry_count < 1:
        l2_retry = True
        t2 = time.perf_counter()
        sql, token_in2, token_out2 = await generate_sql_from_llm(
            settings=settings,
            question=question,
            context_text=context_text,
            compact=True,
        )
        gen_ms += int((time.perf_counter() - t2) * 1000)
        retry_count += 1
        token_in = (token_in or 0) + (token_in2 or 0) if token_in2 else token_in
        token_out = (token_out or 0) + (token_out2 or 0) if token_out2 else token_out

    await _span(
        config,
        "generate_sql",
        t0,
        "success" if sql else "fail",
        {
            "retry_count": retry_count,
            "has_sql": bool(sql),
            "l2_retry": l2_retry,
            "token_in": token_in,
            "token_out": token_out,
            "sql_preview": sql,
            "error_code": None if sql else "LLM_NO_SQL",
            "error_message": None
            if sql
            else "未能生成有效 SQL，请换种问法或标记 badcase",
        },
    )

    if not sql:
        return {
            "status": "fail",
            "error_code": "LLM_NO_SQL",
            "error_message": "未能生成有效 SQL，请换种问法或标记 badcase",
            "latency_ms_sql_gen": gen_ms,
            "retry_count": retry_count,
            "degrade_level": 3,
            "token_in": token_in,
            "token_out": token_out,
        }

    return {
        "raw_sql": sql,
        "degrade_level": 0,
        "latency_ms_sql_gen": gen_ms,
        "retry_count": retry_count,
        "token_in": token_in,
        "token_out": token_out,
        "value_column": "cnt",
        "answer_template": "根据查询结果，共返回 {row_count} 行数据。",
    }


async def validate_sql_node(state: AskGraphState, config: RunnableConfig) -> dict:
    """SELECT only、表白名单、LIMIT。"""
    if state.get("error_code"):
        return {}

    t0 = time.perf_counter()
    c = _cfg(config)
    ctx: UserContext = c["ctx"]
    settings: Settings = c["settings"]
    raw = state.get("raw_sql")
    if not raw:
        await _span(
            config,
            "validate_sql",
            t0,
            "fail",
            {"error_code": "NO_SQL", "error_message": "无 SQL 可校验"},
        )
        return {
            "status": "fail",
            "error_code": "NO_SQL",
            "error_message": "无 SQL 可校验",
            "degrade_level": 3,
        }

    try:
        final_sql = validate_sql(raw, ctx, max_rows=settings.sql_max_rows, settings=settings)
        final_sql = strip_sch_id_for_broad_roles(final_sql, ctx, settings=settings)

        meta_repo = MetaRepository(c["copilot_session"])
        table_names = list(
            dict.fromkeys(
                re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)", final_sql, flags=re.IGNORECASE)
            )
        )
        column_map = await meta_repo.load_active_column_names(table_names)
        validate_sql_columns(final_sql, column_map)

        found = re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)", final_sql, flags=re.IGNORECASE)
        tables_used = ",".join(dict.fromkeys(t.lower() for t in found))
        await _span(config, "validate_sql", t0, "success", {
            "tables_used": tables_used,
            "sql_preview": final_sql,
        })
        return {"final_sql": final_sql, "tables_used": tables_used, "status": "running"}
    except SqlGuardError as exc:
        await _span(
            config,
            "validate_sql",
            t0,
            "fail",
            {"error_code": exc.code, "error_message": exc.message},
        )
        return {
            "status": "fail",
            "error_code": exc.code,
            "error_message": exc.message,
            "validation_error": exc.message,
            "degrade_level": 3,
        }


async def apply_policy(state: AskGraphState, config: RunnableConfig) -> dict:
    """
    学校账户补 sch_id 参数；与 matched 路径共用 params。

    第 7～12 周 `POLICY_SCH_ID_ENABLED=false` 时跳过 sch 注入（§11.7.1）。
    第 13 周由 EffectivePolicy 替代（§11.6）。
    """
    if state.get("error_code"):
        return {}

    t0 = time.perf_counter()
    c = _cfg(config)
    ctx: UserContext = c["ctx"]
    final_sql = state.get("final_sql") or ""
    params = dict(state.get("sql_params") or {})

    matched = state.get("matched")
    if matched is not None:
        params = dict(matched.params)
        if ctx.role == UserRole.SCHOOL and ":sch_id" in final_sql.lower():
            params["sch_id"] = require_school_scope(ctx)
    elif applies_sch_id_filter(ctx, settings=c["settings"]):
        if ":sch_id" not in final_sql.lower() and "sch_id" not in final_sql.lower():
            await _span(config, "apply_policy", t0, "fail", {"error": "MISSING_SCH_ID"})
            return {
                "status": "fail",
                "error_code": "MISSING_SCH_ID",
                "error_message": "学校账户查询必须包含 sch_id 条件",
                "degrade_level": 3,
            }
        try:
            params["sch_id"] = require_school_scope(ctx)
        except PolicyError as exc:
            await _span(config, "apply_policy", t0, "fail", {"error": exc.code})
            return {
                "status": "fail",
                "error_code": exc.code,
                "error_message": exc.message,
                "degrade_level": 3,
            }

    if not applies_sch_id_filter(ctx, settings=c["settings"]):
        stripped_sql = strip_sch_id_for_broad_roles(final_sql, ctx, settings=c["settings"])
        if stripped_sql != final_sql:
            final_sql = stripped_sql
            params.pop("sch_id", None)
            await _span(
                config,
                "apply_policy",
                t0,
                "success",
                {"stripped_sch_id": True},
            )
            return {"sql_params": params, "final_sql": final_sql}

    await _span(config, "apply_policy", t0, "success")
    return {"sql_params": params}


async def execute_sql(state: AskGraphState, config: RunnableConfig) -> dict:
    """业务只读库执行。"""
    if state.get("error_code"):
        return {}

    t0 = time.perf_counter()
    c = _cfg(config)
    ctx: UserContext = c["ctx"]
    settings: Settings = c["settings"]
    final_sql = state.get("final_sql")
    params = state.get("sql_params") or {}

    if not final_sql:
        return {"status": "fail", "error_code": "NO_SQL", "degrade_level": 3}

    final_sql = strip_sch_id_for_broad_roles(final_sql, ctx, settings=settings)
    params = dict(params)
    if not applies_sch_id_filter(ctx, settings=settings):
        params.pop("sch_id", None)

    trace_id = c.get("trace_id", "-")
    logger.info(
        "[trace=%s] %s[%s] 开始执行 sql=%r params=%r",
        trace_id,
        get_node_label("execute_sql"),
        "execute_sql",
        final_sql,
        params,
    )

    try:
        columns, rows = await execute_readonly(
            final_sql,
            params,
            max_rows=settings.sql_max_rows,
        )
        exec_ms = int((time.perf_counter() - t0) * 1000)
        await _span(config, "execute_sql", t0, "success", {"row_count": len(rows)})
        tables = state.get("tables_used") or ""
        if not tables and state.get("matched"):
            tables = ",".join(state["matched"].tables)
        return {
            "columns": columns,
            "rows": rows,
            "latency_ms_sql_exec": exec_ms,
            "tables_used": tables,
            "status": "running",
        }
    except Exception as exc:
        logger.exception(
            "[trace=%s] %s[%s] 执行失败 sql=%r params=%r error=%s",
            trace_id,
            get_node_label("execute_sql"),
            "execute_sql",
            final_sql,
            params,
            exc,
        )
        await _span(
            config,
            "execute_sql",
            t0,
            "fail",
            {
                "error_code": "SQL_EXEC_ERROR",
                "error_message": str(exc),
                "sql_preview": final_sql,
                "params": params,
            },
        )
        return {
            "status": "fail",
            "error_code": "SQL_EXEC_ERROR",
            "error_message": "SQL 执行失败",
            "validation_error": str(exc),
            "degrade_level": 3,
        }


def _format_answer_text(state: AskGraphState) -> str:
    template = state.get("answer_template") or "共 {row_count} 行"
    value_col = state.get("value_column") or "cnt"
    columns = state.get("columns") or []
    rows = state.get("rows") or []
    row_count = len(rows)
    if value_col == "cnt" and rows and columns:
        try:
            idx = columns.index("cnt")
            return template.format(cnt=rows[0][idx], row_count=row_count)
        except (ValueError, IndexError):
            pass
    return template.format(cnt=row_count, row_count=row_count)


async def format_answer(state: AskGraphState, config: RunnableConfig) -> dict:
    """生成一句话回答或 L3 拒答文案；复杂 Agent 路径可选用 LLM 解读。"""
    t0 = time.perf_counter()
    error_code = state.get("error_code")
    rows = state.get("rows") or []
    # 语义验证仅因空结果失败且已耗尽修正：仍返回可读答复，避免多轮记忆链断裂
    if error_code == "VERIFY_FAILED" and not rows:
        answer = _format_answer_text(state) or "查询结果为空，请尝试调整时间范围或筛选条件。"
        await _span(
            config,
            "format_answer",
            t0,
            "success",
            {"answer_preview": answer, "verify_empty_graceful": True},
        )
        return {"answer": answer, "status": "success", "error_code": None, "error_message": None}

    if error_code:
        msg = state.get("error_message") or "无法完成本次问数，请调整问法或联系管理员。"
        await _span(
            config,
            "format_answer",
            t0,
            "fail",
            {
                "error_code": state.get("error_code"),
                "error_message": msg,
            },
        )
        return {"answer": msg, "status": "fail"}

    answer = _format_answer_text(state)
    c = _cfg(config)
    settings: Settings = c["settings"]
    use_agent = state.get("use_agent_path") and not state.get("plan_skipped")
    columns = state.get("columns") or []
    rows = state.get("rows") or []

    if (
        settings.format_answer_llm_enabled
        and use_agent
        and rows
        and len(columns) > 1
    ):
        llm_answer = await _format_answer_with_llm(
            settings,
            question=state.get("normalized_question") or "",
            columns=columns,
            rows=rows,
            fallback=answer,
        )
        if llm_answer:
            answer = llm_answer

    await _span(
        config,
        "format_answer",
        t0,
        "success",
        {"answer_preview": answer, "llm_formatted": use_agent and settings.format_answer_llm_enabled},
    )
    return {"answer": answer, "status": "success"}


async def _format_answer_with_llm(
    settings: Settings,
    *,
    question: str,
    columns: list[str],
    rows: list[list],
    fallback: str,
) -> str | None:
    """复杂多维结果：LLM 生成可读摘要（失败时回退模板）。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agent.llm_sql import build_llm

    llm = build_llm(settings)
    sample = rows[:5]
    system = (
        "你是数据解读助手。根据问句、列名与样例行，用一两句中文总结查询结果。"
        "若列为动态透视（多项目列），说明主要数值；不要编造不存在的数据。"
    )
    user = (
        f"问句：{question}\n列名：{columns}\n"
        f"样例行（最多5行）：{sample}\n总行数：{len(rows)}"
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        text = content.strip()
        return text if len(text) > 4 else None
    except Exception:
        return None


_CORRECTABLE_CODES = frozenset(
    {
        "PARSE_ERROR",
        "NOT_SELECT",
        "NO_TABLE",
        "TABLE_NOT_ALLOWED",
        "MISSING_SCH_ID",
        "SQL_EXEC_ERROR",
        "VERIFY_FAILED",
        "COLUMN_NOT_FOUND",
    }
)


async def correct_sql(state: AskGraphState, config: RunnableConfig) -> dict:
    """校验失败时带错误信息与工具观察重生成 SQL（最多 AGENT_MAX_CORRECT 次）。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    context_text = state.get("context_text") or ""
    context_text = _append_plan_context(context_text, state)
    previous_sql = state.get("raw_sql") or state.get("final_sql") or ""
    error_msg = state.get("validation_error") or state.get("error_message") or "SQL 校验失败"
    correct_count = (state.get("correct_sql_count") or 0) + 1

    sql, token_in, token_out = await generate_sql_from_llm(
        settings=settings,
        question=question,
        context_text=context_text,
        compact=False,
        correction_hint=error_msg,
        previous_sql=previous_sql,
    )

    await _span(
        config,
        "correct_sql",
        t0,
        "success" if sql else "fail",
        {
            "correct_sql_count": correct_count,
            "has_sql": bool(sql),
            "token_in": token_in,
            "token_out": token_out,
            "sql_preview": sql,
            "correction_hint": error_msg,
            "error_code": None if sql else "LLM_NO_SQL",
            "error_message": None if sql else "SQL 修正失败，请换种问法或标记 badcase",
        },
    )

    if not sql:
        return {
            "status": "fail",
            "error_code": "LLM_NO_SQL",
            "error_message": "SQL 修正失败，请换种问法或标记 badcase",
            "correct_sql_count": correct_count,
            "degrade_level": 3,
        }

    return {
        "raw_sql": sql,
        "final_sql": None,
        "error_code": None,
        "error_message": None,
        "validation_error": None,
        "status": "running",
        "correct_sql_count": correct_count,
        "token_in": (state.get("token_in") or 0) + (token_in or 0),
        "token_out": (state.get("token_out") or 0) + (token_out or 0),
    }


def _max_correct_sql() -> int:
    return get_settings().agent_max_correct


def route_after_validate(state: AskGraphState) -> str:
    if state.get("error_code"):
        code = state.get("error_code") or ""
        if (
            state.get("matched") is None
            and (state.get("correct_sql_count") or 0) < _max_correct_sql()
            and code in _CORRECTABLE_CODES
        ):
            return "correct_sql"
        return "format_answer"
    return "apply_policy"


def route_after_execute(state: AskGraphState) -> str:
    """执行失败且可修正时重走 correct_sql；成功则进入 verify_answer。"""
    if state.get("error_code"):
        code = state.get("error_code") or ""
        if (
            state.get("matched") is None
            and (state.get("correct_sql_count") or 0) < _max_correct_sql()
            and code in _CORRECTABLE_CODES
        ):
            return "correct_sql"
        return "verify_answer"
    return "verify_answer"
