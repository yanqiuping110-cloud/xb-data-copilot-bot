"""
认证业务：登录、切换学校、根据 JWT 载荷加载用户。

与 youplus-base-api 登录无关，仅操作 copilot 库 copilot_sys_user。
"""

from app.auth import jwt_tokens
from app.auth.password import verify_password
from app.auth.repositories import UserRepository
from app.core.context import UserRole
from app.db.models.user import SysUser
from config.settings import Settings


class AuthError(Exception):
    """认证/授权业务异常，由 main 注册为 HTTP 响应。"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def schools_from_user(user: SysUser) -> list[tuple[int, str | None]]:
    """ORM 学校绑定 → (sch_id, sch_name) 列表，供 API 响应。"""
    return [(s.sch_id, s.sch_name) for s in user.schools]


def bound_sch_ids(user: SysUser) -> list[int]:
    """用户绑定的全部学校 ID。"""
    return [s.sch_id for s in user.schools]


def default_active_sch_id(user: SysUser) -> int | None:
    """
    登录时若仅绑定一所学校，自动设为当前校（可立即问数）。

    多所绑定须调 switch-school 或前端选校。
    """
    ids = bound_sch_ids(user)
    if user.role == UserRole.SCHOOL.value and len(ids) == 1:
        return ids[0]
    return None


def issue_token_for_user(
    user: SysUser,
    settings: Settings,
    active_sch_id: int | None = None,
) -> tuple[str, int]:
    """按用户角色签发 JWT。"""
    role = UserRole(user.role)
    bound = bound_sch_ids(user) if role == UserRole.SCHOOL else []
    active = active_sch_id
    if role == UserRole.SCHOOL and active is None:
        active = default_active_sch_id(user)
    return jwt_tokens.create_access_token(
        user_id=user.id,
        role=role,
        secret=settings.jwt_secret,
        expire_hours=settings.jwt_expire_hours,
        active_sch_id=active,
        bound_sch_ids=bound,
    )


class AuthService:
    """认证用例封装，供 API 层调用。"""

    def __init__(self, repo: UserRepository, settings: Settings):
        self._repo = repo
        self._settings = settings

    async def login(
        self, username: str, password: str
    ) -> tuple[str, int, SysUser, int | None]:
        """
        用户名密码登录。

        Returns:
            token, expires_in, 用户实体, 自动选中的 active_sch_id（可能为 None）
        """
        user = await self._repo.get_by_username(username)
        if user is None or user.status != 1:
            raise AuthError("INVALID_CREDENTIALS", "用户名或密码错误", 401)
        if not verify_password(password, user.password_hash):
            raise AuthError("INVALID_CREDENTIALS", "用户名或密码错误", 401)
        active = default_active_sch_id(user)
        token, expires_in = issue_token_for_user(user, self._settings, active)
        return token, expires_in, user, active

    async def switch_school(self, user_id: int, sch_id: int) -> tuple[str, int]:
        """学校账户切换当前校，重新签发 token（更新 active_sch_id）。"""
        user = await self._repo.get_by_id(user_id)
        if user is None or user.status != 1:
            raise AuthError("USER_DISABLED", "账户不可用", 403)
        if user.role != UserRole.SCHOOL.value:
            raise AuthError("NOT_SCHOOL_ROLE", "仅学校账户可切换学校", 403)
        bound = bound_sch_ids(user)
        if sch_id not in bound:
            raise AuthError("SCHOOL_FORBIDDEN", "无权切换到该学校", 403)
        token, expires_in = issue_token_for_user(user, self._settings, sch_id)
        return token, expires_in

    async def load_user_from_token_payload(self, payload: dict) -> SysUser:
        """
        根据 JWT 载荷回库校验用户仍存在且启用。

        若 payload.role 与库不一致，说明角色已被超管修改，要求重新登录。
        """
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError) as e:
            raise AuthError("TOKEN_INVALID", "无效的访问令牌", 401) from e
        user = await self._repo.get_by_id(user_id)
        if user is None or user.status != 1:
            raise AuthError("USER_DISABLED", "账户不可用", 403)
        role = payload.get("role")
        if role != user.role:
            raise AuthError("TOKEN_STALE", "权限已变更，请重新登录", 401)
        return user
