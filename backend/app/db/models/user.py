"""
问数用户 ORM：copilot_sys_user、copilot_sys_user_school。

与 ddl_copilot.sql 表结构一致；role 取值 ADMIN / OPERATOR / SCHOOL。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类。"""

    pass


class SysUser(Base):
    """问数系统登录账户（与后台 user 表无关）。"""

    __tablename__ = "copilot_sys_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[int] = mapped_column(default=1)  # 1 启用 0 禁用
    created_by: Mapped[int | None] = mapped_column(BigInteger)  # 创建该账户的超管 id
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        server_default="0",
        comment="逻辑删除：0未删除 1已删除",
    )

    schools: Mapped[list["SysUserSchool"]] = relationship(
        back_populates="user",
    )


class SysUserSchool(Base):
    """学校账户可访问的 sch_id 列表（一对多）。"""

    __tablename__ = "copilot_sys_user_school"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("copilot_sys_user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sch_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sch_name: Mapped[str | None] = mapped_column(String(128))  # 展示用，非权限依据
    deleted: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        server_default="0",
        comment="逻辑删除：0未删除 1已删除",
    )

    user: Mapped[SysUser] = relationship(back_populates="schools")
