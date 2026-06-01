"""
问数库 copilot：异步 SQLAlchemy 引擎与会话工厂。

用于 copilot_sys_user、copilot_ask_*、copilot_audit_log 等表（表名前缀 copilot_）。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """懒加载单例引擎（进程内复用连接池）。"""
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.copilot_database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_copilot_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends：请求级会话，请求结束自动关闭。"""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def check_copilot_connection() -> bool:
    """就绪探针：能否连上 copilot 库。"""
    from sqlalchemy import text

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
