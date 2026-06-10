"""
问数 HTTP 接口：POST /api/v1/ask（LangGraph + L1 + LLM，可选 SSE 流式进度）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.service import handle_ask, handle_ask_cancel, handle_ask_stream, wants_stream
from app.core.context import UserContext
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.schemas.ask import AskCancelRequest, AskCancelResponse, AskRequest, AskResponse
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["ask"])


@router.post(
    "/ask",
    response_model=AskResponse,
    response_model_by_alias=True,
    responses={
        200: {
            "description": "问数结果 JSON，或 options.stream=true 时 SSE 流",
            "content": {
                "application/json": {},
                "text/event-stream": {},
            },
        }
    },
)
async def ask(
    body: AskRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    自然语言问数。

    - 默认：一次性返回 JSON（`AskResponse`）
    - `options.stream=true`：SSE 推送节点进度（`progress`）与最终结果（`done`）
    """
    if wants_stream(body):
        return StreamingResponse(
            handle_ask_stream(body, ctx, session, settings),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return await handle_ask(body, ctx, session, settings)


@router.post(
    "/ask/cancel",
    response_model=AskCancelResponse,
    response_model_by_alias=True,
)
async def ask_cancel(
    body: AskCancelRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> AskCancelResponse:
    """用户主动中断进行中的问数（仅 pending turn）。"""
    ok = await handle_ask_cancel(body.trace_id, ctx, session)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CANCEL_NOT_APPLICABLE",
                    "message": "问数已结束或不存在，无法中断",
                }
            },
        )
    return AskCancelResponse(ok=True, trace_id=body.trace_id)
