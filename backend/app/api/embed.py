"""
Embed Token 签发（超管 / appId+secret）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repositories import UserRepository
from app.auth.service import AuthError
from app.core.context import UserContext, UserRole
from app.core.security import require_admin
from app.db.copilot import get_copilot_session
from app.schemas.base import CamelModel
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/embed", tags=["embed"])


class EmbedTokenRequest(CamelModel):
    user_id: int | None = None
    role: str | None = None
    app_id: str | None = None
    app_secret: str | None = None


class EmbedTokenResponse(CamelModel):
    access_token: str
    expires_in: int
    token_type: str = "Bearer"


def create_embed_token(
    *,
    user_id: int,
    role: UserRole,
    secret: str,
    ttl_sec: int,
    active_sch_id: int | None = None,
    bound_sch_ids: list[int] | None = None,
) -> tuple[str, int]:
    """签发 embed 专用短期 JWT（scope=embed）。"""
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    expires_in = ttl_sec
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "scope": "embed",
        "iat": now,
        "exp": now + timedelta(seconds=ttl_sec),
    }
    if role == UserRole.SCHOOL:
        payload["active_sch_id"] = active_sch_id
        payload["bound_sch_ids"] = bound_sch_ids or []
    token = pyjwt.encode(payload, secret, algorithm="HS256")
    return token, expires_in


async def _issue_for_user(
    *,
    user_id: int,
    role: UserRole | None,
    session: AsyncSession,
    settings: Settings,
) -> EmbedTokenResponse:
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise AuthError("USER_NOT_FOUND", "用户不存在", 404)
    resolved_role = role or UserRole(user.role)
    active_sch_id = None
    bound: list[int] = []
    if resolved_role == UserRole.SCHOOL:
        from app.auth.service import bound_sch_ids

        bound = bound_sch_ids(user)
        if bound:
            active_sch_id = bound[0]
    token, expires_in = create_embed_token(
        user_id=user_id,
        role=resolved_role,
        secret=settings.jwt_secret,
        ttl_sec=settings.embed_token_ttl_sec,
        active_sch_id=active_sch_id,
        bound_sch_ids=bound,
    )
    return EmbedTokenResponse(access_token=token, expires_in=expires_in)


@router.post("/token", response_model=EmbedTokenResponse, response_model_by_alias=True)
async def issue_embed_token_app(
    body: EmbedTokenRequest,
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbedTokenResponse:
    """第三方 appId/secret 换 embed token（需 EMBED_ENABLED=true）。"""
    if not settings.embed_enabled:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "EMBED_DISABLED", "message": "嵌入功能未启用"}},
        )
    if not body.app_id or not body.app_secret:
        raise AuthError("FORBIDDEN", "需要 appId 与 appSecret", 403)
    if (
        body.app_id != settings.embed_app_id
        or body.app_secret != settings.embed_app_secret
        or not settings.embed_app_id
    ):
        raise AuthError("FORBIDDEN", "appId 或 appSecret 无效", 403)
    if body.user_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "USER_REQUIRED", "message": "需指定 userId"}},
        )
    role = UserRole(body.role) if body.role else None
    return await _issue_for_user(
        user_id=body.user_id,
        role=role,
        session=session,
        settings=settings,
    )


@router.post(
    "/token/admin",
    response_model=EmbedTokenResponse,
    response_model_by_alias=True,
)
async def issue_embed_token_admin(
    body: EmbedTokenRequest,
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbedTokenResponse:
    """超管为指定用户签发 embed token。"""
    if not settings.embed_enabled:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "EMBED_DISABLED", "message": "嵌入功能未启用"}},
        )
    if body.user_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "USER_REQUIRED", "message": "需指定 userId"}},
        )
    role = UserRole(body.role) if body.role else None
    return await _issue_for_user(
        user_id=body.user_id,
        role=role,
        session=session,
        settings=settings,
    )
