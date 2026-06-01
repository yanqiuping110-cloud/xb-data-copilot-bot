"""
超管用户管理 API 的 Pydantic 模型。
"""

from app.core.context import UserRole
from app.schemas.auth import BoundSchool, UserInfo
from app.schemas.base import CamelModel


class SchoolBinding(CamelModel):
    """创建/更新用户时的学校绑定项。"""

    sch_id: int
    sch_name: str | None = None


class CreateUserRequest(CamelModel):
    """POST /admin/users。"""

    username: str
    password: str
    role: UserRole
    display_name: str | None = None
    sch_ids: list[int] | None = None  # 简写：仅 ID 列表
    schools: list[SchoolBinding] | None = None  # 或带校名


class PatchUserRequest(CamelModel):
    """PATCH /admin/users/{id}：部分更新。"""

    status: int | None = None  # 1 启用 0 禁用
    password: str | None = None
    display_name: str | None = None


class ReplaceSchoolsRequest(CamelModel):
    """PUT /admin/users/{id}/schools：全量覆盖绑定。"""

    sch_ids: list[int] | None = None
    schools: list[SchoolBinding] | None = None


class UserListResponse(CamelModel):
    """GET /admin/users 分页列表。"""

    items: list[UserInfo]
    total: int
    page: int
    page_size: int
