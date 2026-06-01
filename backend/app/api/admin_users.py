"""
超管用户管理 HTTP 接口（仅 role=ADMIN）。

路径前缀：/api/v1/admin/users
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.auth.repositories import UserRepository
from app.auth.service import AuthError
from app.core.context import UserContext, UserRole
from app.core.security import require_admin
from app.db.copilot import get_copilot_session
from app.schemas.admin import (
    CreateUserRequest,
    PatchUserRequest,
    ReplaceSchoolsRequest,
    UserListResponse,
)
from app.schemas.auth import BoundSchool, UserInfo

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])


def _normalize_schools(
    sch_ids: list[int] | None,
    schools: list | None,
) -> list[tuple[int, str | None]]:
    """兼容请求体 schIds 或 schools 两种传法。"""
    if schools:
        return [(s.sch_id, s.sch_name) for s in schools]
    if sch_ids:
        return [(sid, None) for sid in sch_ids]
    return []


def _user_info(user) -> UserInfo:
    info = UserInfo(
        id=user.id,
        username=user.username,
        role=UserRole(user.role),
        display_name=user.display_name,
    )
    if user.role == UserRole.SCHOOL.value:
        info.bound_schools = [
            BoundSchool(sch_id=s.sch_id, sch_name=s.sch_name) for s in user.schools
        ]
    return info


@router.post("", response_model=UserInfo, response_model_by_alias=True, status_code=201)
async def create_user(
    body: CreateUserRequest,
    admin: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> UserInfo:
    """创建运营或学校账户；不可创建 ADMIN（仅 seed）。"""
    if body.role == UserRole.ADMIN:
        raise AuthError("INVALID_ROLE", "不能通过接口创建超管", 400)
    repo = UserRepository(session)
    if await repo.username_exists(body.username):
        raise AuthError("USERNAME_EXISTS", "用户名已存在", 409)

    schools = _normalize_schools(body.sch_ids, body.schools)
    if body.role == UserRole.SCHOOL and not schools:
        raise AuthError("SCHOOLS_REQUIRED", "学校账户必须绑定至少一所学校", 400)

    user = await repo.create_user(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role.value,
        display_name=body.display_name,
        created_by=admin.user_id,
        schools=schools if body.role == UserRole.SCHOOL else None,
    )
    await session.commit()
    return _user_info(user)


@router.get("", response_model=UserListResponse, response_model_by_alias=True)
async def list_users(
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    role: UserRole | None = None,
) -> UserListResponse:
    """分页用户列表，可按角色筛选。"""
    repo = UserRepository(session)
    users, total = await repo.list_users(
        page=page,
        page_size=page_size,
        role=role.value if role else None,
    )
    return UserListResponse(
        items=[_user_info(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{user_id}", response_model=UserInfo, response_model_by_alias=True)
async def patch_user(
    user_id: int,
    body: PatchUserRequest,
    admin: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> UserInfo:
    """更新状态、密码或显示名；禁止禁用其他超管。"""
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise AuthError("USER_NOT_FOUND", "用户不存在", 404)
    if user.role == UserRole.ADMIN.value and user.id != admin.user_id:
        if body.status is not None and body.status == 0:
            raise AuthError("FORBIDDEN", "不能禁用其他超管", 403)

    password_hash = hash_password(body.password) if body.password else None
    user = await repo.update_user(
        user,
        status=body.status,
        password_hash=password_hash,
        display_name=body.display_name,
    )
    await session.commit()
    user = await repo.get_by_id(user_id)
    return _user_info(user)


@router.put("/{user_id}/schools", response_model=UserInfo, response_model_by_alias=True)
async def replace_schools(
    user_id: int,
    body: ReplaceSchoolsRequest,
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> UserInfo:
    """全量替换学校账户的 sch_id 绑定。"""
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise AuthError("USER_NOT_FOUND", "用户不存在", 404)
    if user.role != UserRole.SCHOOL.value:
        raise AuthError("NOT_SCHOOL_USER", "仅学校账户可维护学校绑定", 400)

    schools = _normalize_schools(body.sch_ids, body.schools)
    if not schools:
        raise AuthError("SCHOOLS_REQUIRED", "至少绑定一所学校", 400)

    await repo.replace_schools(user_id, schools)
    await session.commit()
    user = await repo.get_by_id(user_id)
    return _user_info(user)
