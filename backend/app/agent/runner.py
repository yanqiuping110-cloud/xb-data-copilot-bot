"""
运行 LangGraph 问数图并映射为 API 响应（支持 SSE 流式进度）。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_ask_graph
from app.memory.memory_service import MemoryService
from app.memory.session_service import SessionService
from app.ask.column_labels import localize_result_columns
from app.agent.log_utils import get_node_label, summarize_state_update
from app.agent.state import AskGraphState
from app.agent.streaming import done_event, error_event, progress_event, text_delta_event, thinking_delta_event
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
from app.policy.effective_policy import EffectivePolicy, load_effective_policy
from app.policy.scope_injector import apply_scope_to_sql, validate_scope_literals
from app.schemas.ask import AskRequest, AskResponse, IntermediateSqlResult
from app.schemas.chart import ChartSpec
from app.sql.whitelist import refresh_allowed_tables
from config.settings import Settings

logger = get_logger("ask")

USER_CANCELLED_MESSAGE = "用户主动中断"


async def _turn_status_isolated(trace_id: str) -> str | None:
    """
    用独立短会话读取 turn status。

    流式路径里图 worker 与主循环会并发跑；共用请求级 AsyncSession
    会触发 concurrent operations are not permitted。
    """
    from app.db.copilot import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        return await tracer.get_turn_status(session, trace_id)


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
    answer_delta_queue: asyncio.Queue[str] | None = config["configurable"].get("answer_delta_queue")
    thinking_delta_queue: asyncio.Queue[str] | None = config["configurable"].get(
        "thinking_delta_queue"
    )
    logger.info("[trace=%s] 问数开始 stream=true question=%r", trace_id, question)

    # 统一出口：节点 running / thinking / text_delta / 图 updates 都进此队列，保证长节点中途也能刷到前端
    out_q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    stop_workers = asyncio.Event()

    from app.agent.progress_callback import AskNodeStartProgressCallback

    node_start_cb = AskNodeStartProgressCallback(out_q)
    # RunnableConfig callbacks：节点开始立即推 running
    existing_cbs = list(config.get("callbacks") or [])
    existing_cbs.append(node_start_cb)
    config = {**config, "callbacks": existing_cbs}

    async def _delta_poller() -> None:
        while not stop_workers.is_set():
            for frame in _drain_thinking_delta_queue(thinking_delta_queue):
                await out_q.put(("sse", frame))
            for frame in _drain_answer_delta_queue(answer_delta_queue):
                await out_q.put(("sse", frame))
            await asyncio.sleep(0.05)
        for frame in _drain_thinking_delta_queue(thinking_delta_queue):
            await out_q.put(("sse", frame))
        for frame in _drain_answer_delta_queue(answer_delta_queue):
            await out_q.put(("sse", frame))

    async def _astream_worker() -> None:
        try:
            async for chunk in get_ask_graph().astream(initial, config, stream_mode="updates"):
                await out_q.put(("chunk", chunk))
                # 独立会话查取消态，避免与下一节点写库并发踩同一 AsyncSession
                if await _turn_status_isolated(trace_id) == "cancelled":
                    break
        except Exception as exc:
            logger.exception("[trace=%s] astream_worker 异常: %s", trace_id, exc)
            await out_q.put(("error", exc))
        finally:
            await out_q.put(("end", None))

    poller_task = asyncio.create_task(_delta_poller())
    stream_task = asyncio.create_task(_astream_worker())

    try:
        while True:
            kind, payload = await out_q.get()
            if kind == "sse":
                yield payload
                continue
            if kind == "error":
                raise payload
            if kind == "end":
                break
            # chunk: 节点完成
            chunk = payload
            if await _turn_status_isolated(trace_id) == "cancelled":
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
                duration_ms = collector.duration_for_node(node_name)
                yield progress_event(
                    node_name,
                    detail=detail,
                    status="done",
                    duration_ms=duration_ms,
                )

        if await _turn_status_isolated(trace_id) == "cancelled":
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
        if response.status not in (
            "success",
            "need_clarification",
            "chitchat",
            "out_of_scope",
        ):
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
    finally:
        stop_workers.set()
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass
        await poller_task


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
        # 客户端指定的新 session（如评测 eval-*）：保留 id，首轮 upsert 会创建；
        # 仅当 session 已属于他人时才另起新对话。
        if await session_svc.session_belongs_to_other_user(session_id, ctx.user_id):
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

    policy: EffectivePolicy | None = None
    if settings.policy_data_scope_enabled:
        policy = await load_effective_policy(
            copilot_session, ctx, settings=settings
        )
        ctx = ctx.model_copy(update={"effective_policy": policy})

    initial: AskGraphState = {
        "trace_id": trace_id,
        "question": question,
        "degrade_level": 0,
        "retry_count": 0,
        "correct_sql_count": 0,
        "sql_params": {},
    }
    if body.clarification_answers:
        initial["clarification_answers"] = [
            a.model_dump() for a in body.clarification_answers
        ]
    if body.clarification_thread_id:
        initial["clarification_thread_id"] = body.clarification_thread_id

    collector = TraceLogCollector(trace_id, stream=stream)
    answer_delta_queue: asyncio.Queue[str] | None = asyncio.Queue() if stream else None
    thinking_delta_queue: asyncio.Queue[str] | None = None
    if stream and settings.llm_thinking_enabled and settings.llm_thinking_stream:
        if not settings.llm_thinking_stream_admin_only or ctx.role == UserRole.ADMIN:
            thinking_delta_queue = asyncio.Queue()
    config = {
        "recursion_limit": settings.graph_recursion_limit,
        "configurable": {
            "trace_id": trace_id,
            "session_id": session_id,
            "copilot_session": copilot_session,
            "ctx": ctx,
            "settings": settings,
            "trace_log_collector": collector,
            "answer_delta_queue": answer_delta_queue,
            "thinking_delta_queue": thinking_delta_queue,
        }
    }
    return trace_id, question, session_id, initial, config, t0


def _drain_answer_delta_queue(
    queue: asyncio.Queue[str] | None,
) -> list[str]:
    frames: list[str] = []
    if queue is None:
        return frames
    while not queue.empty():
        try:
            delta = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if delta:
            frames.append(text_delta_event(delta))
    return frames


def _drain_thinking_delta_queue(
    queue: asyncio.Queue | None,
) -> list[str]:
    frames: list[str] = []
    if queue is None:
        return frames
    while not queue.empty():
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if not item:
            continue
        if isinstance(item, dict):
            delta = item.get("delta") or ""
            node = item.get("node")
        else:
            delta = str(item)
            node = None
        if delta:
            frames.append(thinking_delta_event(delta, node=node))
    return frames


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
    # need_clarification / chitchat / out_of_scope 不算 fail
    dialogue_statuses = {"need_clarification", "chitchat", "out_of_scope"}
    error_message = (
        final_state.get("error_message")
        if status not in ("success", *dialogue_statuses)
        else None
    )
    row_count = len(final_state.get("rows") or [])
    latency_ms_total = _elapsed_ms(t0)

    clarification = _clarification_from_state(final_state)
    dialogue_act = final_state.get("dialogue_act")

    display_columns = localize_result_columns(
        final_state.get("columns"),
        question=question,
        state=final_state,
    )
    result_json = build_result_json(
        answer=final_state.get("answer"),
        columns=display_columns,
        rows=final_state.get("rows"),
        error_message=final_state.get("error_message")
        if status not in ("success", *dialogue_statuses)
        else None,
        intermediate_results=_serialize_intermediate_for_storage(
            final_state.get("intermediate_results")
        ),
        assembly_mode=final_state.get("assembly_mode"),
        chart_spec=final_state.get("chart_spec"),
        visualization_intent=final_state.get("visualization_intent"),
        clarification=clarification,
        dialogue_act=dialogue_act,
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
        # 成功出数立即清 pending，避免串话
        if settings.session_memory_enabled:
            mem_clear = MemoryService(copilot_session, settings)
            await mem_clear.clear_pending_clarification(session_id, ctx.user_id)
    await copilot_session.commit()

    if status == "success" and settings.session_memory_enabled:
        mem_svc = MemoryService(copilot_session, settings)
        updated_memory = await mem_svc.load_session_memory(session_id, ctx.user_id)
        if updated_memory.turns:
            await mem_svc.update_session_summary(session_id, ctx.user_id, updated_memory)
            await copilot_session.commit()

    chart_spec_obj = _chart_spec_from_state(final_state)
    clarification_obj = None
    if clarification:
        from app.schemas.ask import ClarificationPayload

        try:
            clarification_obj = ClarificationPayload.model_validate(clarification)
        except Exception:
            clarification_obj = None

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
        if status not in ("success", "need_clarification", "chitchat", "out_of_scope")
        else None,
        assembly_mode=final_state.get("assembly_mode"),
        intermediate_results=_serialize_intermediate_for_response(
            final_state.get("intermediate_results"),
            include_sql=ctx.role == UserRole.ADMIN,
        ),
        chart_spec=chart_spec_obj,
        chart_image_url=None,
        visualization_intent=final_state.get("visualization_intent"),
        dialogue_act=dialogue_act,
        clarification=clarification_obj,
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
    try:
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
    except Exception:
        logger.exception(
            "[trace=%s] finish_turn 失败，改用独立会话落库",
            trace_id,
        )
        try:
            await copilot_session.rollback()
        except Exception:
            pass
        from app.db.copilot import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            await tracer.finish_turn(
                session,
                trace_id=trace_id,
                status="fail",
                final_sql=None,
                latency_ms_total=latency_ms_total,
                latency_ms_first_token=collector.latency_ms_first_token,
                error_code=error_code,
                trace_log=trace_log,
                result_json=build_result_json(error_message=error_message),
            )
            await session.commit()


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
    if node_name == "do_recall_sql_examples":
        return {"count": len(update.get("l1_candidates") or [])}
    if node_name == "select_l1_examples":
        selected = update.get("selected_l1_examples") or []
        return {"count": len(selected), "selectedIds": [s.get("id") for s in selected[:5]]}
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
    if node_name == "execute_plan_sql_step":
        steps = update.get("sql_steps") or []
        last = steps[-1] if steps else {}
        return {
            "stepId": last.get("step_id"),
            "goal": last.get("goal"),
            "rowCount": last.get("row_count"),
            "stepIndex": update.get("sql_exec_step_index"),
            "intermediatePreview": _intermediate_preview(update.get("intermediate_results")),
        }
    if node_name == "assemble_result":
        return {
            "assemblyMode": update.get("assembly_mode"),
            "rowCount": len(update.get("rows") or []),
            "columnCount": len(update.get("columns") or []),
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


_INTERMEDIATE_RESPONSE_MAX_ROWS = 10


def _intermediate_preview(intermediate: list | None) -> list[dict] | None:
    if not intermediate:
        return None
    return [
        {
            "stepId": ir.get("step_id"),
            "goal": ir.get("goal"),
            "rowCount": ir.get("row_count"),
            "columns": (ir.get("columns") or [])[:6],
        }
        for ir in intermediate[-3:]
    ]


def _clarification_from_state(state: AskGraphState) -> dict | None:
    """从 state 组装 clarification 字典（供 result_json / AskResponse）。"""
    payload = state.get("_clarification_payload")
    if isinstance(payload, dict):
        return payload
    ask_user = state.get("ask_user_question")
    if not ask_user and state.get("status") != "need_clarification":
        return None
    from app.agent.ask_user_payload import clarification_payload_dict

    pending = state.get("pending_clarification") or {}
    return clarification_payload_dict(
        ask_user=ask_user if isinstance(ask_user, dict) else None,
        missing_slots=list(state.get("missing_slots") or []),
        partial_question=state.get("resolved_question") or state.get("normalized_question"),
        thread_id=pending.get("thread_id"),
        clarify_question=state.get("clarify_question"),
        clarify_options=state.get("clarify_options"),
    )


def _chart_spec_from_state(state: AskGraphState) -> ChartSpec | None:
    raw = state.get("chart_spec")
    if not raw:
        return None
    try:
        return ChartSpec.model_validate(raw)
    except Exception:
        return None


def _serialize_intermediate_for_response(
    intermediate: list | None,
    *,
    include_sql: bool,
) -> list[IntermediateSqlResult] | None:
    if not intermediate:
        return None
    out: list[IntermediateSqlResult] = []
    for ir in intermediate:
        rows = ir.get("rows") or []
        out.append(
            IntermediateSqlResult(
                step_id=ir.get("step_id"),
                goal=ir.get("goal"),
                sql=ir.get("sql") if include_sql else None,
                columns=ir.get("columns"),
                rows=[list(r) for r in rows[:_INTERMEDIATE_RESPONSE_MAX_ROWS]],
                row_count=ir.get("row_count") or len(rows),
            )
        )
    return out


def _serialize_intermediate_for_storage(intermediate: list | None) -> list[dict] | None:
    if not intermediate:
        return None
    stored: list[dict] = []
    for ir in intermediate:
        rows = ir.get("rows") or []
        stored.append(
            {
                "step_id": ir.get("step_id"),
                "goal": ir.get("goal"),
                "columns": ir.get("columns"),
                "rows": [list(r) for r in rows[:_INTERMEDIATE_RESPONSE_MAX_ROWS]],
                "row_count": ir.get("row_count") or len(rows),
            }
        )
    return stored
