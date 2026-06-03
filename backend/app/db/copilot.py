"""
问数库 copilot：异步 SQLAlchemy 引擎与会话工厂。

策略（见 app/db/sql_policy.py）：
  MYSQL_COPILOT_DATABASE 允许 DML（用户/审计等）；
  运行时禁止 DDL——表结构变更仅 scripts/sql/copilot/V*.sql 人工执行；
  禁止物理 DELETE——删除须 UPDATE deleted=1（0 未删除，1 已删除）。
"""

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.sql_policy import assert_copilot_runtime_sql
from config.settings import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_guard_installed = False


def _install_copilot_sql_guard(engine) -> None:
    """问数库连接：拦截 DDL 与物理 DELETE。"""

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _block_unsafe_sql(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        from app.db.sql_policy import (
            CopilotDdlForbiddenError,
            CopilotPhysicalDeleteForbiddenError,
        )

        try:
            assert_copilot_runtime_sql(statement)
        except (CopilotDdlForbiddenError, CopilotPhysicalDeleteForbiddenError) as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from exc


def get_engine():
    """懒加载单例引擎（进程内复用连接池）。"""
    global _engine, _session_factory, _guard_installed
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.copilot_database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        if not _guard_installed:
            _install_copilot_sql_guard(_engine)
            _guard_installed = True
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
