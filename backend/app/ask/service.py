"""
问数编排入口：委托 LangGraph 7 节点流水线。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import run_ask_graph
from app.core.context import UserContext
from app.schemas.ask import AskRequest, AskResponse
from config.settings import Settings


async def handle_ask(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AskResponse:
    """处理单次问数请求（LangGraph）。"""
    return await run_ask_graph(body, ctx, copilot_session, settings)
