"""
用户与学校绑定数据访问（copilot 库）。

对应表：copilot_sys_user、copilot_sys_user_school。
查询默认过滤 deleted=0；删除一律 UPDATE deleted=1，禁止物理 DELETE。
"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.user import SysUser, SysUserSchool

_NOT_DELETED = 0


class UserRepository:
    """copilot_sys_user 仓储，会话由 FastAPI Depends 注入。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_username(self, username: str) -> SysUser | None:
        """登录：按用户名查未逻辑删除用户，预加载有效学校绑定。"""
        stmt = (
            select(SysUser)
            .where(SysUser.username == username, SysUser.deleted == _NOT_DELETED)
            .options(selectinload(SysUser.schools.and_(SysUserSchool.deleted == _NOT_DELETED)))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> SysUser | None:
        """按主键查未逻辑删除用户，含有效学校列表。"""
        stmt = (
            select(SysUser)
            .where(SysUser.id == user_id, SysUser.deleted == _NOT_DELETED)
            .options(selectinload(SysUser.schools.and_(SysUserSchool.deleted == _NOT_DELETED)))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        role: str | None = None,
    ) -> tuple[list[SysUser], int]:
        """超管用户列表（分页，不含已逻辑删除用户）。"""
        filters = [SysUser.deleted == _NOT_DELETED]
        if role:
            filters.append(SysUser.role == role)
        count_stmt = select(func.count()).select_from(SysUser).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(SysUser)
            .where(*filters)
            .options(selectinload(SysUser.schools.and_(SysUserSchool.deleted == _NOT_DELETED)))
            .order_by(SysUser.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
        display_name: str | None,
        created_by: int | None,
        schools: list[tuple[int, str | None]] | None = None,
    ) -> SysUser:
        """创建运营/学校账户；学校账户可附带绑定校。"""
        user = SysUser(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            status=1,
            created_by=created_by,
            deleted=_NOT_DELETED,
        )
        self._session.add(user)
        await self._session.flush()
        if schools:
            for sch_id, sch_name in schools:
                self._session.add(
                    SysUserSchool(
                        user_id=user.id,
                        sch_id=sch_id,
                        sch_name=sch_name,
                        deleted=_NOT_DELETED,
                    )
                )
        await self._session.flush()
        await self._session.refresh(user, ["schools"])
        return user

    async def update_user(
        self,
        user: SysUser,
        *,
        status: int | None = None,
        password_hash: str | None = None,
        display_name: str | None = None,
    ) -> SysUser:
        """禁用/启用、改密、改显示名。"""
        if status is not None:
            user.status = status
        if password_hash is not None:
            user.password_hash = password_hash
        if display_name is not None:
            user.display_name = display_name
        await self._session.flush()
        return user

    async def replace_schools(
        self,
        user_id: int,
        schools: list[tuple[int, str | None]],
    ) -> None:
        """全量覆盖学校绑定：旧绑定逻辑删除，新绑定插入或恢复 deleted=0。"""
        await self._session.execute(
            update(SysUserSchool)
            .where(
                SysUserSchool.user_id == user_id,
                SysUserSchool.deleted == _NOT_DELETED,
            )
            .values(deleted=1)
        )
        for sch_id, sch_name in schools:
            stmt = select(SysUserSchool).where(
                SysUserSchool.user_id == user_id,
                SysUserSchool.sch_id == sch_id,
            )
            row = (await self._session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                row.deleted = _NOT_DELETED
                row.sch_name = sch_name
            else:
                self._session.add(
                    SysUserSchool(
                        user_id=user_id,
                        sch_id=sch_id,
                        sch_name=sch_name,
                        deleted=_NOT_DELETED,
                    )
                )
        await self._session.flush()

    async def username_exists(self, username: str, exclude_id: int | None = None) -> bool:
        """创建用户前查重（仅未逻辑删除用户）。"""
        stmt = select(SysUser.id).where(
            SysUser.username == username,
            SysUser.deleted == _NOT_DELETED,
        )
        if exclude_id is not None:
            stmt = stmt.where(SysUser.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
