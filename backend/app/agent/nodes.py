"""
LangGraph 7 节点实现。
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.context_retriever import build_retrieval_context
from app.agent.llm_sql import generate_sql_from_llm
from app.agent.state import AskGraphState
from app.ask.query_match import ensure_can_run, match_question_async
from app.ask.semantic_repository import SemanticRepository
from app.core.context import UserContext, UserRole
from app.observability import tracer
from app.policy.role_policy import PolicyError, applies_sch_id_filter, require_school_scope
from app.sql.executor import execute_readonly
from app.sql.guard import SqlGuardError, validate_sql
from app.sql.whitelist import refresh_allowed_tables
from config.settings import Settings

_MAX_QUESTION_LEN = 2000


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


async def _span(
    config: RunnableConfig,
    node_name: str,
    t0: float,
    status: str,
    detail: dict | None = None,
) -> None:
    c = _cfg(config)
    session = c["copilot_session"]
    await tracer.insert_span(
        session,
        trace_id=c["trace_id"],
        node_name=node_name,
        started_at=datetime.now(),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        status=status,
        detail=detail,
    )


async def normalize_question(state: AskGraphState, config: RunnableConfig) -> dict:
    """清洗问句、截断长度。"""
    t0 = time.perf_counter()
    q = (state.get("question") or "").strip()
    normalized = q[:_MAX_QUESTION_LEN]
    await _span(config, "normalize_question", t0, "success", {"length": len(normalized)})
    return {"normalized_question": normalized, "status": "running"}


async def retrieve_context(state: AskGraphState, config: RunnableConfig) -> dict:
    """术语 + 表说明 + 相似样例 SQL。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    repo = SemanticRepository(c["copilot_session"])
    question = state.get("normalized_question") or state.get("question") or ""
    try:
        context_text = await build_retrieval_context(question, repo)
        status = "success"
    except Exception as exc:
        context_text = "【检索失败，仅依赖表白名单】\n" + str(exc)
        status = "degraded"
    await _span(config, "retrieve_context", t0, status, {"chars": len(context_text)})
    return {"context_text": context_text}


async def match_curated(state: AskGraphState, config: RunnableConfig) -> dict:
    """L1 库内样例 + MVP 兜底匹配。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    ctx: UserContext = c["ctx"]
    session = c["copilot_session"]
    question = state.get("normalized_question") or ""

    matched = await match_question_async(question, ctx, session)
    detail = {"matched": matched is not None, "source": matched.match_source if matched else None}
    await _span(config, "match_curated", t0, "success" if matched else "fail", detail)

    if matched is None:
        return {"matched": None, "degrade_level": 0}

    try:
        ensure_can_run(matched, ctx)
    except PolicyError as exc:
        return {
            "matched": None,
            "status": "fail",
            "error_code": exc.code,
            "error_message": exc.message,
        }

    return {
        "matched": matched,
        "raw_sql": matched.sql,
        "sql_params": dict(matched.params),
        "tables_used": ",".join(matched.tables),
        "degrade_level": matched.degrade_level,
        "value_column": matched.value_column,
        "answer_template": matched.answer_template,
    }


async def generate_sql(state: AskGraphState, config: RunnableConfig) -> dict:
    """LLM 生成 SQL（L0）；失败可 L2 重试一次。"""
    if state.get("matched") is not None:
        return {}

    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    context_text = state.get("context_text") or ""
    retry_count = state.get("retry_count") or 0

    sql, token_in, token_out = await generate_sql_from_llm(
        settings=settings,
        question=question,
        context_text=context_text,
        compact=False,
    )
    gen_ms = int((time.perf_counter() - t0) * 1000)

    if not sql and retry_count < 1:
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
        {"retry_count": retry_count, "has_sql": bool(sql)},
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
        await _span(config, "validate_sql", t0, "fail", {"error": "NO_SQL"})
        return {
            "status": "fail",
            "error_code": "NO_SQL",
            "error_message": "无 SQL 可校验",
            "degrade_level": 3,
        }

    try:
        final_sql = validate_sql(raw, ctx, max_rows=settings.sql_max_rows)
        found = re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)", final_sql, flags=re.IGNORECASE)
        tables_used = ",".join(dict.fromkeys(t.lower() for t in found))
        await _span(config, "validate_sql", t0, "success")
        return {"final_sql": final_sql, "tables_used": tables_used, "status": "running"}
    except SqlGuardError as exc:
        await _span(config, "validate_sql", t0, "fail", {"error": exc.code})
        return {
            "status": "fail",
            "error_code": exc.code,
            "error_message": exc.message,
            "degrade_level": 3,
        }


async def apply_policy(state: AskGraphState, config: RunnableConfig) -> dict:
    """学校账户补 sch_id 参数；与 matched 路径共用 params。"""
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
    elif applies_sch_id_filter(ctx):
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

    await _span(config, "apply_policy", t0, "success")
    return {"sql_params": params}


async def execute_sql(state: AskGraphState, config: RunnableConfig) -> dict:
    """业务只读库执行。"""
    if state.get("error_code"):
        return {}

    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    final_sql = state.get("final_sql")
    params = state.get("sql_params") or {}

    if not final_sql:
        return {"status": "fail", "error_code": "NO_SQL", "degrade_level": 3}

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
    except Exception:
        await _span(config, "execute_sql", t0, "fail", {"error": "SQL_EXEC_ERROR"})
        return {
            "status": "fail",
            "error_code": "SQL_EXEC_ERROR",
            "error_message": "SQL 执行失败",
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
    """生成一句话回答或 L3 拒答文案。"""
    t0 = time.perf_counter()
    if state.get("error_code"):
        msg = state.get("error_message") or "无法完成本次问数，请调整问法或联系管理员。"
        await _span(config, "format_answer", t0, "fail")
        return {"answer": msg, "status": "fail"}

    answer = _format_answer_text(state)
    await _span(config, "format_answer", t0, "success")
    return {"answer": answer, "status": "success"}


def route_after_match(state: AskGraphState) -> str:
    """命中 L1/MVP 则跳过 LLM。"""
    if state.get("error_code"):
        return "format_answer"
    if state.get("matched") is not None:
        return "validate_sql"
    return "generate_sql"


def route_after_validate(state: AskGraphState) -> str:
    if state.get("error_code"):
        return "format_answer"
    return "apply_policy"
