"""
运行 LangGraph 问数图并映射为 API 响应。
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_ask_graph
from app.agent.state import AskGraphState
from app.ask.exceptions import AskError
from app.core.context import UserContext, UserRole
from app.observability import tracer
from app.policy.role_policy import PolicyError, require_school_scope
from app.schemas.ask import AskRequest, AskResponse
from app.sql.whitelist import refresh_allowed_tables
from config.settings import Settings


async def run_ask_graph(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AskResponse:
    """执行 7 节点 LangGraph 流水线。"""
    trace_id = body.trace_id or ctx.trace_id or str(uuid.uuid4())
    question = body.question.strip()
    if not question:
        raise AskError("EMPTY_QUESTION", "问题不能为空")

    if ctx.role == UserRole.SCHOOL:
        require_school_scope(ctx)

    t0 = time.perf_counter()
    await tracer.insert_turn_start(
        copilot_session,
        trace_id=trace_id,
        session_id=body.session_id,
        ctx=ctx,
        question=question,
    )
    await copilot_session.commit()

    await refresh_allowed_tables(copilot_session)

    initial: AskGraphState = {
        "trace_id": trace_id,
        "question": question,
        "degrade_level": 0,
        "retry_count": 0,
        "sql_params": {},
    }

    config = {
        "configurable": {
            "trace_id": trace_id,
            "copilot_session": copilot_session,
            "ctx": ctx,
            "settings": settings,
        }
    }

    try:
        final_state = await get_ask_graph().ainvoke(initial, config)
    except PolicyError:
        await tracer.finish_turn(
            copilot_session,
            trace_id=trace_id,
            status="fail",
            final_sql=None,
            latency_ms_total=_elapsed_ms(t0),
            error_code="POLICY_ERROR",
        )
        await copilot_session.commit()
        raise

    status = final_state.get("status") or "fail"
    error_code = final_state.get("error_code")
    row_count = len(final_state.get("rows") or [])

    await tracer.finish_turn(
        copilot_session,
        trace_id=trace_id,
        status=status,
        final_sql=final_state.get("final_sql"),
        latency_ms_total=_elapsed_ms(t0),
        latency_ms_sql_exec=final_state.get("latency_ms_sql_exec"),
        latency_ms_sql_gen=final_state.get("latency_ms_sql_gen"),
        row_count=row_count,
        error_code=error_code,
        degrade_level=final_state.get("degrade_level") or 0,
        retry_count=final_state.get("retry_count") or 0,
        token_in=final_state.get("token_in"),
        token_out=final_state.get("token_out"),
    )
    await tracer.insert_audit(
        copilot_session,
        ctx=ctx,
        trace_id=trace_id,
        question=question,
        sql=final_state.get("final_sql"),
        tables_used=final_state.get("tables_used"),
        row_count=row_count,
    )
    await copilot_session.commit()

    return AskResponse(
        trace_id=trace_id,
        status=status,
        degrade_level=final_state.get("degrade_level") or 0,
        sql=final_state.get("final_sql"),
        columns=final_state.get("columns"),
        rows=final_state.get("rows"),
        answer=final_state.get("answer"),
        latency_ms=_elapsed_ms(t0),
        error_code=error_code,
        error_message=final_state.get("error_message")
        if status != "success"
        else None,
    )


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
