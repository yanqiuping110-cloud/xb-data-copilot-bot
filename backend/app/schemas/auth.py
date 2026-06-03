"""
认证相关 API 的 Pydantic 模型（登录、切换学校、当前用户）。
"""

from app.core.context import UserRole
from app.schemas.base import CamelModel


class LoginRequest(CamelModel):
    """POST /auth/login 请求体。"""

    username: str
    password: str


class BoundSchool(CamelModel):
    """学校账户绑定的单所学校。"""

    sch_id: int
    sch_name: str | None = None


class UserInfo(CamelModel):
    """返回给前端的用户摘要（不含密码）。"""

    id: int
    username: str
    role: UserRole
    display_name: str | None = None
    status: int | None = None  # 1 启用 0 禁用（用户管理列表展示）
    bound_schools: list[BoundSchool] | None = None
    active_sch_id: int | None = None


class LoginResponse(CamelModel):
    """登录 / 切换学校成功响应。"""

    access_token: str
    expires_in: int
    user: UserInfo


class SwitchSchoolRequest(CamelModel):
    """POST /auth/switch-school：目标 sch_id。"""

    sch_id: int


class MeResponse(CamelModel):
    """GET /auth/me 响应。"""

    user: UserInfo
