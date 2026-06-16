"""
业务库：只读连接（问数执行 SQL 时使用）。

策略（见 app/db/sql_policy.py）：
  MYSQL_BUSINESS_DATABASE 禁止一切 DML 与 DDL，应用层仅允许 SELECT。
  数据库账号应仅授予 SELECT 权限（双保险）。
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_business_engine():
    """懒加载业务库引擎（只读账号）。"""
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.business_database_url,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_business_session_factory() -> async_sessionmaker[AsyncSession]:
    get_business_engine()
    assert _session_factory is not None
    return _session_factory


async def get_business_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends：业务库只读会话（introspect 等）。"""
    factory = get_business_session_factory()
    async with factory() as session:
        yield session


async def check_business_connection() -> bool:
    """就绪探针：能否连上业务只读库。"""
    try:
        engine = get_business_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
