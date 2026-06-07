"""
运行 LangGraph 问数图并映射为 API 响应（支持 SSE 流式进度）。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_ask_graph
from app.ask.column_labels import localize_result_columns
from app.agent.log_utils import get_node_label, summarize_state_update
from app.agent.state import AskGraphState
from app.agent.streaming import done_event, error_event, progress_event
from app.ask.exceptions import AskError
from app.core.context import UserContext, UserRole
from app.core.log_config import get_logger
from app.observability import tracer
from app.observability.trace_log import (
    TraceLogCollector,
    build_final_summary,
    resolve_error_node,
)
from app.policy.role_policy import PolicyError, require_school_scope
from app.schemas.ask import AskRequest, AskResponse
from app.sql.whitelist import refresh_allowed_tables
from config.settings import Settings

logger = get_logger("ask")


async def run_ask_graph(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AskResponse:
    """执行多阶段 LangGraph 问数流水线（一次性返回）。"""
    trace_id, question, initial, config, t0 = await _prepare_ask_run(
        body, ctx, copilot_session, settings, stream=False
    )
    collector: TraceLogCollector = config["configurable"]["trace_log_collector"]
    logger.info("[trace=%s] 问数开始 stream=false question=%r", trace_id, question)
    try:
        final_state = await get_ask_graph().ainvoke(initial, config)
    except PolicyError as exc:
        logger.warning("[trace=%s] 问数失败 code=POLICY_ERROR", trace_id)
        await _finish_turn_on_fatal(
            copilot_session,
            trace_id,
            t0,
            collector=collector,
            error_code=exc.code,
            error_message=exc.message,
        )
        raise
    except Exception as exc:
        logger.exception("[trace=%s] 问数失败 code=GRAPH_ERROR: %s", trace_id, exc)
        await _finish_turn_on_fatal(
            copilot_session,
            trace_id,
            t0,
            collector=collector,
            error_code="GRAPH_ERROR",
            error_message=str(exc),
        )
        raise

    logger.info(
        "[trace=%s] 问数完成 status=%s summary=%s",
        trace_id,
        final_state.get("status"),
        summarize_state_update(final_state),
    )

    return await _finalize_ask_run(
        copilot_session,
        ctx=ctx,
        trace_id=trace_id,
        question=question,
        final_state=final_state,
        t0=t0,
        collector=collector,
    )


async def stream_ask_graph(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AsyncIterator[str]:
    """
    SSE 流式问数：每完成一个 LangGraph 节点推送 progress，结束时推送 done。

    Yields:
        SSE 文本帧（`event: progress|done|error`）。
    """
    trace_id, question, initial, config, t0 = await _prepare_ask_run(
        body, ctx, copilot_session, settings, stream=True
    )
    collector: TraceLogCollector = config["configurable"]["trace_log_collector"]
    accumulated: AskGraphState = dict(initial)
    first_progress_sent = False
    logger.info("[trace=%s] 问数开始 stream=true question=%r", trace_id, question)

    try:
        async for chunk in get_ask_graph().astream(initial, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                if update:
                    accumulated.update(update)
                detail = _progress_detail(node_name, update)
                logger.info(
                    "[trace=%s] 节点完成 %s[%s] detail=%s output=%s",
                    trace_id,
                    get_node_label(node_name),
                    node_name,
                    detail,
                    summarize_state_update(update),
                )
                if not first_progress_sent:
                    collector.mark_first_token(_elapsed_ms(t0))
                    first_progress_sent = True
                yield progress_event(node_name, detail=detail)

        response = await _finalize_ask_run(
            copilot_session,
            ctx=ctx,
            trace_id=trace_id,
            question=question,
            final_state=accumulated,
            t0=t0,
            collector=collector,
        )
        yield done_event(response)
        if response.status != "success":
            logger.error(
                "[trace=%s] 问数流结束 status=%s error_code=%s error_message=%s sql=%r",
                trace_id,
                response.status,
                response.error_code,
                response.error_message,
                response.sql,
            )
        else:
            logger.info(
                "[trace=%s] 问数流结束 status=%s latency_ms=%s row_count=%s",
                trace_id,
                response.status,
                response.latency_ms,
                len(response.rows or []),
            )
    except PolicyError as exc:
        logger.warning(
            "[trace=%s] 问数流错误 code=%s message=%s",
            trace_id,
            exc.code,
            exc.message,
        )
        await _finish_turn_on_fatal(
            copilot_session,
            trace_id,
            t0,
            collector=collector,
            error_code=exc.code,
            error_message=exc.message,
        )
        yield error_event(exc.code, exc.message)
    except Exception as exc:
        logger.exception(
            "[trace=%s] 问数流错误 code=STREAM_ERROR: %s",
            trace_id,
            exc,
        )
        await _finish_turn_on_fatal(
            copilot_session,
            trace_id,
            t0,
            collector=collector,
            error_code="STREAM_ERROR",
            error_message=str(exc),
        )
        yield error_event("STREAM_ERROR", str(exc))


async def _prepare_ask_run(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
    *,
    stream: bool,
) -> tuple[str, str, AskGraphState, dict, float]:
    """问数前置：校验、写 turn、刷新白名单、构造初始状态。"""
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
        "correct_sql_count": 0,
        "sql_params": {},
    }

    collector = TraceLogCollector(trace_id, stream=stream)
    config = {
        "configurable": {
            "trace_id": trace_id,
            "copilot_session": copilot_session,
            "ctx": ctx,
            "settings": settings,
            "trace_log_collector": collector,
        }
    }
    return trace_id, question, initial, config, t0


async def _finalize_ask_run(
    copilot_session: AsyncSession,
    *,
    ctx: UserContext,
    trace_id: str,
    question: str,
    final_state: AskGraphState,
    t0: float,
    collector: TraceLogCollector,
) -> AskResponse:
    """写 turn/audit 并构造 AskResponse。"""
    status = final_state.get("status") or "fail"
    error_code = final_state.get("error_code")
    error_message = final_state.get("error_message") if status != "success" else None
    row_count = len(final_state.get("rows") or [])
    latency_ms_total = _elapsed_ms(t0)

    trace_log = collector.to_json(
        status=status,
        latency_ms_total=latency_ms_total,
        error_code=error_code,
        error_message=error_message,
        error_node=resolve_error_node(collector, error_code=error_code),
        final=build_final_summary(final_state),
    )

    await tracer.finish_turn(
        copilot_session,
        trace_id=trace_id,
        status=status,
        final_sql=final_state.get("final_sql"),
        latency_ms_total=latency_ms_total,
        latency_ms_first_token=collector.latency_ms_first_token,
        latency_ms_sql_exec=final_state.get("latency_ms_sql_exec"),
        latency_ms_sql_gen=final_state.get("latency_ms_sql_gen"),
        row_count=row_count,
        error_code=error_code,
        degrade_level=final_state.get("degrade_level") or 0,
        retry_count=final_state.get("retry_count") or 0,
        token_in=final_state.get("token_in"),
        token_out=final_state.get("token_out"),
        trace_log=trace_log,
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

    display_columns = localize_result_columns(
        final_state.get("columns"),
        question=question,
        state=final_state,
    )

    return AskResponse(
        trace_id=trace_id,
        status=status,
        degrade_level=final_state.get("degrade_level") or 0,
        sql=final_state.get("final_sql"),
        columns=display_columns,
        rows=final_state.get("rows"),
        answer=final_state.get("answer"),
        latency_ms=_elapsed_ms(t0),
        error_code=error_code,
        error_message=final_state.get("error_message")
        if status != "success"
        else None,
    )


async def _finish_turn_on_fatal(
    copilot_session: AsyncSession,
    trace_id: str,
    t0: float,
    *,
    collector: TraceLogCollector,
    error_code: str,
    error_message: str,
) -> None:
    collector.append_fatal(
        error_code=error_code,
        error_message=error_message,
    )
    latency_ms_total = _elapsed_ms(t0)
    trace_log = collector.to_json(
        status="fail",
        latency_ms_total=latency_ms_total,
        error_code=error_code,
        error_message=error_message,
        error_node=resolve_error_node(collector, error_code=error_code) or "fatal",
    )
    await tracer.finish_turn(
        copilot_session,
        trace_id=trace_id,
        status="fail",
        final_sql=None,
        latency_ms_total=latency_ms_total,
        latency_ms_first_token=collector.latency_ms_first_token,
        error_code=error_code,
        trace_log=trace_log,
    )
    await copilot_session.commit()


def _progress_detail(node_name: str, update: dict) -> dict | None:
    """从节点增量状态提取可展示的进度摘要。"""
    if not update:
        return None
    if node_name == "extract_keywords" and update.get("keywords"):
        return {"keywords": update["keywords"][:8]}
    if node_name in ("do_recall_tables", "recall_tables"):
        tables = update.get("recall_tables") or []
        return {"count": len(tables)}
    if node_name in ("do_recall_columns", "recall_columns"):
        cols = update.get("recall_columns") or []
        return {"count": len(cols)}
    if node_name in ("do_recall_metrics", "recall_metrics"):
        return {"count": len(update.get("recall_metrics") or [])}
    if node_name in ("do_recall_field_values", "recall_field_values"):
        return {"count": len(update.get("recall_field_values") or [])}
    if node_name == "match_curated":
        matched = update.get("matched")
        return {"matched": matched is not None}
    if node_name == "generate_sql":
        return {"hasSql": bool(update.get("raw_sql"))}
    if node_name == "execute_sql":
        rows = update.get("rows") or []
        return {"rowCount": len(rows)}
    if node_name == "build_llm_context" and update.get("context_text"):
        return {"chars": len(update["context_text"])}
    return None


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
