"""
认证 HTTP 接口：登录、切换学校、当前用户信息。

路径前缀：/api/v1/auth
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repositories import UserRepository
from app.auth.service import AuthError, AuthService, schools_from_user
from app.core.context import UserContext, UserRole
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.schemas.auth import (
    BoundSchool,
    LoginRequest,
    LoginResponse,
    MeResponse,
    SwitchSchoolRequest,
    UserInfo,
)
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_info(user, active_sch_id: int | None = None) -> UserInfo:
    """ORM → API 用户信息；学校角色附带绑定校与当前校。"""
    info = UserInfo(
        id=user.id,
        username=user.username,
        role=UserRole(user.role),
        display_name=user.display_name,
    )
    if user.role == UserRole.SCHOOL.value:
        info.bound_schools = [
            BoundSchool(sch_id=sid, sch_name=sname) for sid, sname in schools_from_user(user)
        ]
        info.active_sch_id = active_sch_id
    return info


@router.post("/login", response_model=LoginResponse, response_model_by_alias=True)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """用户名密码登录，返回 JWT（accessToken）与用户摘要。"""
    repo = UserRepository(session)
    auth = AuthService(repo, settings)
    token, expires_in, user, active = await auth.login(body.username, body.password)
    await session.commit()
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=_user_info(user, active),
    )


@router.post("/switch-school", response_model=LoginResponse, response_model_by_alias=True)
async def switch_school(
    body: SwitchSchoolRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """学校账户切换当前校，须在新 token 的 boundSchIds 内。"""
    if ctx.role != UserRole.SCHOOL:
        raise AuthError("NOT_SCHOOL_ROLE", "仅学校账户可切换学校", 403)
    repo = UserRepository(session)
    auth = AuthService(repo, settings)
    token, expires_in = await auth.switch_school(ctx.user_id, body.sch_id)
    user = await repo.get_by_id(ctx.user_id)
    await session.commit()
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=_user_info(user, body.sch_id),
    )


@router.get("/me", response_model=MeResponse, response_model_by_alias=True)
async def me(
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> MeResponse:
    """根据 Bearer token 返回当前用户（含学校绑定）。"""
    repo = UserRepository(session)
    user = await repo.get_by_id(ctx.user_id)
    if user is None:
        raise AuthError("USER_NOT_FOUND", "用户不存在", 404)
    return MeResponse(user=_user_info(user, ctx.active_sch_id))
