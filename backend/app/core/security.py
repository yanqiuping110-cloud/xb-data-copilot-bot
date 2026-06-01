"""
FastAPI 依赖注入：从请求头解析 JWT，构建 UserContext。

支持 Authorization: Bearer 与兼容头 token:（与部分旧前端一致）。
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import jwt_tokens
from app.auth.repositories import UserRepository
from app.auth.service import AuthError, AuthService, bound_sch_ids
from app.core.context import UserContext, UserRole
from app.db.copilot import get_copilot_session
from config.settings import Settings, get_settings

# auto_error=False：无 Bearer 时继续检查 token 头
_bearer = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    token_header: str | None,
) -> str | None:
    """优先 Bearer，其次 token 头。"""
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    if token_header:
        return token_header.strip()
    return None


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    token_header: Annotated[str | None, Header(alias="token")] = None,
    session: Annotated[AsyncSession, Depends(get_copilot_session)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> UserContext:
    """
    解析 JWT 并回库校验用户仍有效（防禁用后 token 未过期）。

    学校账户：从 JWT 取 active_sch_id；仅绑定一所时自动作为当前校。
    """
    raw = _extract_token(credentials, token_header)
    if not raw:
        raise AuthError("UNAUTHORIZED", "未登录", 401)

    try:
        payload = jwt_tokens.decode_access_token(raw, settings.jwt_secret)
    except jwt_tokens.TokenError as e:
        raise AuthError(e.code, e.message, 401) from e

    repo = UserRepository(session)
    auth = AuthService(repo, settings)
    user = await auth.load_user_from_token_payload(payload)

    role = UserRole(user.role)
    active_sch_id = None
    bound = []
    if role == UserRole.SCHOOL:
        bound = bound_sch_ids(user)
        raw_active = payload.get("active_sch_id")
        if raw_active is not None:
            active_sch_id = int(raw_active)
        elif len(bound) == 1:
            # 仅一所绑定校时，与登录逻辑一致，默认可问数
            active_sch_id = bound[0]

    client_ip = request.client.host if request.client else None
    return UserContext(
        trace_id=str(uuid.uuid4()),
        user_id=user.id,
        username=user.username,
        role=role,
        active_sch_id=active_sch_id,
        bound_sch_ids=bound,
        client_ip=client_ip,
    )


async def require_admin(
    ctx: Annotated[UserContext, Depends(get_current_user)],
) -> UserContext:
    """超管专用依赖：非 ADMIN 返回 403。"""
    if ctx.role != UserRole.ADMIN:
        raise AuthError("FORBIDDEN", "需要管理员权限", 403)
    return ctx
