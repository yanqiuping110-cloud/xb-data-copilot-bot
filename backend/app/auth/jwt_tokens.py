"""
JWT 访问令牌签发与解析（HS256）。

Payload 约定见 DEVELOPMENT_PLAN §2.5.2：
- 所有角色：sub（user_id）、role、exp
- SCHOOL 额外：active_sch_id、bound_sch_ids
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.context import UserRole


class TokenError(Exception):
    """令牌无效或过期，映射为 401。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def create_access_token(
    *,
    user_id: int,
    role: UserRole,
    secret: str,
    expire_hours: int,
    active_sch_id: int | None = None,
    bound_sch_ids: list[int] | None = None,
) -> tuple[str, int]:
    """
    签发 accessToken。

    Returns:
        (token 字符串, expires_in 秒)
    """
    expires_in = expire_hours * 3600
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(hours=expire_hours),
    }
    # 仅学校账户携带校维度，避免运营/超管 token 被篡改 sch_id
    if role == UserRole.SCHOOL:
        payload["active_sch_id"] = active_sch_id
        payload["bound_sch_ids"] = bound_sch_ids or []
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token, expires_in


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    """校验签名与过期时间，失败抛出 TokenError。"""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise TokenError("TOKEN_EXPIRED", "登录已过期，请重新登录") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("TOKEN_INVALID", "无效的访问令牌") from e
