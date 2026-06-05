"""
问数编排入口：委托 LangGraph 流水线（支持 SSE 流式进度）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import run_ask_graph, stream_ask_graph
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
    return await run_ask_graph(body, ctx, copilot_session, settings)


async def handle_ask_stream(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AsyncIterator[str]:
    """处理流式问数请求（SSE 文本帧）。"""
    async for frame in stream_ask_graph(body, ctx, copilot_session, settings):
        yield frame
