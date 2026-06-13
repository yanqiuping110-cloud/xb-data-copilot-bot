"""
运行 LangGraph 问数图并映射为 API 响应（支持 SSE 流式进度）。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_ask_graph
from app.memory.memory_service import MemoryService
from app.memory.session_service import SessionService
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
    build_result_json,
    resolve_error_node,
)
from app.ask.chat_client import sanitize_chat_sql
from app.policy.role_policy import PolicyError, require_school_scope
from app.schemas.ask import AskRequest, AskResponse
from app.sql.whitelist import refresh_allowed_tables
from config.settings import Settings

logger = get_logger("ask")

USER_CANCELLED_MESSAGE = "用户主动中断"


async def cancel_ask_run(
    copilot_session: AsyncSession,
    *,
    trace_id: str,
    user_id: int,
) -> bool:
    """用户主动中断进行中的问数（仅 pending turn）。"""
    updated = await tracer.finish_turn_user_cancelled(
        copilot_session,
        trace_id=trace_id,
        user_id=user_id,
    )
    if updated:
        await copilot_session.commit()
    return updated


async def run_ask_graph(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AskResponse:
    """执行多阶段 LangGraph 问数流水线（一次性返回）。"""
    trace_id, question, session_id, initial, config, t0 = await _prepare_ask_run(
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
        from langgraph.errors import GraphRecursionError

        if isinstance(exc, GraphRecursionError):
            logger.warning(
                "[trace=%s] 问数图步数超限 recursion_limit=%s",
                trace_id,
                settings.graph_recursion_limit,
            )
            final_state = {
                "status": "fail",
                "error_code": "GRAPH_RECURSION",
                "error_message": "问数步骤过多已中止，请简化问法或稍后重试",
                "degrade_level": 3,
            }
            return await _finalize_ask_run(
                copilot_session,
                settings=settings,
                ctx=ctx,
                trace_id=trace_id,
                session_id=session_id,
                question=question,
                final_state=final_state,
                t0=t0,
                collector=collector,
            )
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
        settings=settings,
        ctx=ctx,
        trace_id=trace_id,
        session_id=session_id,
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
    trace_id, question, session_id, initial, config, t0 = await _prepare_ask_run(
        body, ctx, copilot_session, settings, stream=True
    )
    collector: TraceLogCollector = config["configurable"]["trace_log_collector"]
    accumulated: AskGraphState = dict(initial)
    first_progress_sent = False
    logger.info("[trace=%s] 问数开始 stream=true question=%r", trace_id, question)

    try:
        async for chunk in get_ask_graph().astream(initial, config, stream_mode="updates"):
            if await tracer.get_turn_status(copilot_session, trace_id) == "cancelled":
                logger.info("[trace=%s] 检测到用户中断，停止流水线", trace_id)
                break
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

        if await tracer.get_turn_status(copilot_session, trace_id) == "cancelled":
            yield done_event(_cancelled_response(trace_id, session_id, t0))
            return

        response = await _finalize_ask_run(
            copilot_session,
            settings=settings,
            ctx=ctx,
            trace_id=trace_id,
            session_id=session_id,
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
    except asyncio.CancelledError:
        logger.info("[trace=%s] 连接断开，记录用户中断", trace_id)
        await _finish_turn_on_user_cancel(
            copilot_session,
            trace_id=trace_id,
            user_id=ctx.user_id,
            t0=t0,
            collector=collector,
        )
        raise
    except Exception as exc:
        from langgraph.errors import GraphRecursionError

        if isinstance(exc, GraphRecursionError):
            logger.warning(
                "[trace=%s] 问数流图步数超限 recursion_limit=%s",
                trace_id,
                settings.graph_recursion_limit,
            )
            response = await _finalize_ask_run(
                copilot_session,
                settings=settings,
                ctx=ctx,
                trace_id=trace_id,
                session_id=session_id,
                question=question,
                final_state={
                    "status": "fail",
                    "error_code": "GRAPH_RECURSION",
                    "error_message": "问数步骤过多已中止，请简化问法或稍后重试",
                    "degrade_level": 3,
                },
                t0=t0,
                collector=collector,
            )
            yield done_event(response)
            return
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
) -> tuple[str, str, str, AskGraphState, dict, float]:
    """问数前置：校验、写 turn、刷新白名单、构造初始状态。"""
    trace_id = body.trace_id or ctx.trace_id or str(uuid.uuid4())
    question = body.question.strip()
    if not question:
        raise AskError("EMPTY_QUESTION", "问题不能为空")

    if ctx.role == UserRole.SCHOOL and settings.policy_sch_id_enabled:
        # 第 13 周前：仅 POLICY_SCH_ID_ENABLED=true 时强制校维度（§11.7.1）
        require_school_scope(ctx)

    session_svc = SessionService(copilot_session, settings)
    session_id = body.session_id
    if not session_id:
        session_id = await session_svc.create_session(ctx)
    elif not await session_svc.verify_owner(session_id, ctx.user_id):
        session_id = await session_svc.create_session(ctx)

    t0 = time.perf_counter()
    await tracer.insert_turn_start(
        copilot_session,
        trace_id=trace_id,
        session_id=session_id,
        ctx=ctx,
        question=question,
    )
    await session_svc.upsert_on_ask(session_id, ctx, question, success=False)
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
        "recursion_limit": settings.graph_recursion_limit,
        "configurable": {
            "trace_id": trace_id,
            "session_id": session_id,
            "copilot_session": copilot_session,
            "ctx": ctx,
            "settings": settings,
            "trace_log_collector": collector,
        }
    }
    return trace_id, question, session_id, initial, config, t0


async def _finalize_ask_run(
    copilot_session: AsyncSession,
    *,
    settings: Settings,
    ctx: UserContext,
    trace_id: str,
    session_id: str,
    question: str,
    final_state: AskGraphState,
    t0: float,
    collector: TraceLogCollector,
) -> AskResponse:
    """写 turn/audit 并构造 AskResponse。"""
    if await tracer.get_turn_status(copilot_session, trace_id) == "cancelled":
        return _cancelled_response(trace_id, session_id, t0)

    status = final_state.get("status") or "fail"
    error_code = final_state.get("error_code")
    error_message = final_state.get("error_message") if status != "success" else None
    row_count = len(final_state.get("rows") or [])
    latency_ms_total = _elapsed_ms(t0)

    display_columns = localize_result_columns(
        final_state.get("columns"),
        question=question,
        state=final_state,
    )
    result_json = build_result_json(
        answer=final_state.get("answer"),
        columns=display_columns,
        rows=final_state.get("rows"),
        error_message=final_state.get("error_message") if status != "success" else None,
    )

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
        result_json=result_json,
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

    session_svc = SessionService(copilot_session, settings)
    if status == "success":
        await session_svc.upsert_on_ask(session_id, ctx, question, success=True)
    await copilot_session.commit()

    if status == "success" and settings.session_memory_enabled:
        mem_svc = MemoryService(copilot_session, settings)
        updated_memory = await mem_svc.load_session_memory(session_id, ctx.user_id)
        if updated_memory.turns:
            await mem_svc.update_session_summary(session_id, ctx.user_id, updated_memory)
            await copilot_session.commit()

    return AskResponse(
        trace_id=trace_id,
        session_id=session_id,
        status=status,
        degrade_level=final_state.get("degrade_level") or 0,
        sql=sanitize_chat_sql(ctx, final_state.get("final_sql")),
        columns=display_columns,
        rows=final_state.get("rows"),
        answer=final_state.get("answer"),
        latency_ms=_elapsed_ms(t0),
        error_code=error_code,
        error_message=final_state.get("error_message")
        if status != "success"
        else None,
    )


async def _finish_turn_on_user_cancel(
    copilot_session: AsyncSession,
    *,
    trace_id: str,
    user_id: int,
    t0: float,
    collector: TraceLogCollector,
) -> None:
    latency_ms_total = _elapsed_ms(t0)
    collector.append_fatal(
        error_code="USER_CANCELLED",
        error_message=USER_CANCELLED_MESSAGE,
    )
    trace_log = collector.to_json(
        status="cancelled",
        latency_ms_total=latency_ms_total,
        error_code="USER_CANCELLED",
        error_message=USER_CANCELLED_MESSAGE,
        error_node=resolve_error_node(collector, error_code="USER_CANCELLED"),
    )
    updated = await tracer.finish_turn_user_cancelled(
        copilot_session,
        trace_id=trace_id,
        user_id=user_id,
        latency_ms_total=latency_ms_total,
        latency_ms_first_token=collector.latency_ms_first_token,
        trace_log=trace_log,
    )
    if updated:
        await copilot_session.commit()


def _cancelled_response(trace_id: str, session_id: str, t0: float) -> AskResponse:
    return AskResponse(
        trace_id=trace_id,
        session_id=session_id,
        status="cancelled",
        error_code="USER_CANCELLED",
        error_message=USER_CANCELLED_MESSAGE,
        latency_ms=_elapsed_ms(t0),
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
        result_json=build_result_json(error_message=error_message),
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
    if node_name == "generate_sql":
        return {"hasSql": bool(update.get("raw_sql"))}
    if node_name == "execute_sql":
        rows = update.get("rows") or []
        return {"rowCount": len(rows)}
    if node_name == "build_llm_context" and update.get("context_text"):
        return {"chars": len(update["context_text"])}
    if node_name == "plan_question" and update.get("plan"):
        plan = update["plan"]
        return {
            "complexity": plan.get("complexity"),
            "stepCount": len(plan.get("steps") or []),
            "skipped": update.get("plan_skipped"),
            "tools": [o.get("tool") for o in (update.get("tool_observations") or [])[:5]],
        }
    if node_name == "agent_loop":
        tools = [s.get("tool") for s in (update.get("agent_steps") or []) if s.get("tool")]
        return {
            "stepCount": update.get("agent_step_count"),
            "done": update.get("agent_loop_done"),
            "tool": tools[-1] if tools else None,
            "tools": tools[-5:],
        }
    if node_name == "build_agent_context" and update.get("context_text"):
        return {"chars": len(update["context_text"])}
    if node_name == "generate_sql_step":
        return {
            "hasSql": bool(update.get("raw_sql")),
            "sqlStepCount": len(update.get("sql_steps") or []),
        }
    if node_name == "verify_answer":
        vr = update.get("verify_result") or {}
        return {
            "passed": update.get("verify_passed"),
            "reason": vr.get("reason"),
            "attempts": update.get("verify_attempts"),
        }
    return None


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
