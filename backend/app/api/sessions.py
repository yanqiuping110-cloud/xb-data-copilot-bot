"""
对话 Session API：列表、创建、删除、消息历史。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.ask.chat_client import sanitize_chat_sql
from app.memory.session_service import SessionError, SessionService
from app.schemas.sessions import (
    SessionCreateResponse,
    SessionItem,
    SessionListResponse,
    SessionMessageItem,
    SessionMessagesResponse,
)
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["sessions"])


def _session_error(exc: SessionError):
    from fastapi import HTTPException

    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )


@router.get("/sessions", response_model=SessionListResponse, response_model_by_alias=True)
async def list_sessions(
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionListResponse:
    """当前用户对话列表（最多 SESSION_MAX_PER_USER 条）。"""
    svc = SessionService(session, settings)
    rows = await svc.list_sessions(ctx.user_id)
    items = [
        SessionItem(
            session_id=r.session_id,
            title=r.title,
            turn_count=r.turn_count,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return SessionListResponse(items=items, max_per_user=settings.session_max_per_user)


@router.post("/sessions", response_model=SessionCreateResponse, response_model_by_alias=True)
async def create_session(
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionCreateResponse:
    """创建新对话。"""
    svc = SessionService(session, settings)
    try:
        session_id = await svc.create_session(ctx)
        await session.commit()
    except SessionError as exc:
        _session_error(exc)
    return SessionCreateResponse(session_id=session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """逻辑删除对话。"""
    svc = SessionService(session, settings)
    ok = await svc.delete_session(session_id, ctx.user_id)
    if not ok:
        _session_error(SessionError("NOT_FOUND", "对话不存在或无权删除", 404))
    await session.commit()
    return {"ok": True}


@router.get(
    "/sessions/{session_id}/messages",
    response_model=SessionMessagesResponse,
    response_model_by_alias=True,
)
async def get_session_messages(
    session_id: str,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionMessagesResponse:
    """加载对话 UI 历史（与 Memory 同源 copilot_ask_turn）。"""
    svc = SessionService(session, settings)
    try:
        rows = await svc.list_messages(session_id, ctx.user_id)
    except SessionError as exc:
        _session_error(exc)
    messages = [
        SessionMessageItem(
            trace_id=r["trace_id"],
            question=r["question"],
            final_sql=sanitize_chat_sql(ctx, r.get("final_sql")),
            status=r["status"],
            row_count=r.get("row_count"),
            answer=r.get("answer"),
            columns=r.get("columns"),
            rows=r.get("rows"),
            error_message=r.get("error_message"),
            latency_ms=r.get("latency_ms"),
            created_at=r.get("created_at"),
        )
        for r in rows
    ]
    return SessionMessagesResponse(session_id=session_id, messages=messages)
