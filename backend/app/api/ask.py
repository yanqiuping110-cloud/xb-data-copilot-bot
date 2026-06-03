"""
问数 HTTP 接口：POST /api/v1/ask（LangGraph 7 节点 + L1 + LLM）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.service import handle_ask
from app.core.context import UserContext
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.schemas.ask import AskRequest, AskResponse
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["ask"])


@router.post("/ask", response_model=AskResponse, response_model_by_alias=True)
async def ask(
    body: AskRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskResponse:
    """自然语言问数（LangGraph：retrieve_context → L1/MVP → LLM generate_sql）。"""
    return await handle_ask(body, ctx, session, settings)
