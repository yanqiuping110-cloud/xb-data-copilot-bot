"""
用户偏好 Memory API。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.memory.memory_service import MemoryService
from app.schemas.memory_prefs import (
    PreferenceItem,
    PreferenceListResponse,
    PreferenceUpsertRequest,
)
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.get("/preferences", response_model=PreferenceListResponse, response_model_by_alias=True)
async def list_preferences(
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PreferenceListResponse:
    """当前用户显式偏好列表。"""
    svc = MemoryService(session, settings)
    prefs = await svc.load_user_preferences(ctx.user_id)
    return PreferenceListResponse(
        items=[
            PreferenceItem(
                pref_key=p.pref_key,
                pref_value=p.pref_value,
                source=p.source,
            )
            for p in prefs
        ]
    )


@router.put("/preferences", response_model=PreferenceListResponse, response_model_by_alias=True)
async def upsert_preferences(
    body: PreferenceUpsertRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PreferenceListResponse:
    """批量 upsert 偏好（key 白名单）。"""
    svc = MemoryService(session, settings)
    saved = await svc.upsert_preferences(ctx.user_id, body.preferences)
    await session.commit()
    return PreferenceListResponse(
        items=[
            PreferenceItem(pref_key=p.pref_key, pref_value=p.pref_value, source="explicit")
            for p in saved
        ]
    )


@router.delete("/preferences")
async def delete_preferences(
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    keys: str | None = Query(None, description="逗号分隔的 pref_key，空则清空全部"),
) -> dict:
    """清空或按 key 删除偏好。"""
    svc = MemoryService(session, settings)
    key_list = [k.strip() for k in keys.split(",") if k.strip()] if keys else None
    count = await svc.delete_preferences(ctx.user_id, key_list)
    await session.commit()
    return {"deleted": count}
