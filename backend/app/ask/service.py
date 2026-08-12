"""
问数编排入口：委托 LangGraph 流水线（支持 SSE 流式进度）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import cancel_ask_run, run_ask_graph, stream_ask_graph
from app.core.context import UserContext
from app.schemas.ask import AskRequest, AskResponse
from config.settings import Settings


def wants_stream(body: AskRequest) -> bool:
    """是否启用 SSE 流式问数进度。"""
    return bool(body.options and body.options.stream)


async def handle_ask(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AskResponse:
    """处理单次问数请求（一次性 JSON 响应）。"""
    if (settings.llm_mode or "").strip().lower() == "fixture":
        from app.demo.fixture_ask import handle_fixture_ask

        return await handle_fixture_ask(body, ctx, copilot_session, settings)
    return await run_ask_graph(body, ctx, copilot_session, settings)


async def handle_ask_stream(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AsyncIterator[str]:
    """处理流式问数请求（SSE 文本帧）。"""
    if (settings.llm_mode or "").strip().lower() == "fixture":
        import json

        from app.demo.fixture_ask import handle_fixture_ask

        resp = await handle_fixture_ask(body, ctx, copilot_session, settings)
        yield f"event: done\ndata: {json.dumps(resp.model_dump(by_alias=True), ensure_ascii=False)}\n\n"
        return
    async for frame in stream_ask_graph(body, ctx, copilot_session, settings):
        yield frame


async def handle_ask_cancel(
    trace_id: str,
    ctx: UserContext,
    copilot_session: AsyncSession,
) -> bool:
    """用户主动中断问数。"""
    return await cancel_ask_run(
        copilot_session,
        trace_id=trace_id,
        user_id=ctx.user_id,
    )
