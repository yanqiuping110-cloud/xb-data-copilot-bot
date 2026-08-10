"""
业务库：只读连接（问数执行 SQL 时使用）。

策略（见 app/db/sql_policy.py）：
  业务库禁止一切 DML 与 DDL，应用层仅允许 SELECT。
  数据库账号应仅授予 SELECT 权限（双保险）。

连接优先来自管理台默认数据源（runtime_config），否则回退 env。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.system.connectors import registry
from app.system.connectors.base import ConnectParams
from app.system.runtime_config import resolve_business_dsn
from app.system.sql_context import dsn_to_connect_params

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_sync_engine = None
_sync_session_factory = None
_engine_url: str | None = None
_engine_mode: str | None = None  # async | sync | clickhouse_http


def _connector_for_dsn():
    dsn = resolve_business_dsn()
    return registry.get(dsn.db_type), dsn


def get_business_engine():
    """懒加载业务库引擎（只读账号）；DSN 变更后需 invalidate。"""
    global _engine, _session_factory, _sync_engine, _sync_session_factory, _engine_url, _engine_mode
    dsn = resolve_business_dsn()
    conn = registry.get(dsn.db_type)
    url = dsn.sqlalchemy_url
    mode = "async"
    if conn is not None and not getattr(conn, "uses_async_engine", True):
        if dsn.db_type == "clickhouse":
            mode = "clickhouse_http"
        else:
            mode = "sync"

    if _engine is not None and _engine_url == url and _engine_mode == mode:
        return _engine
    if _sync_engine is not None and _engine_url == url and _engine_mode == mode:
        return _sync_engine

    # 重建
    if _engine is not None:
        # dispose sync in invalidate
        pass

    _engine_url = url
    _engine_mode = mode

    if mode == "async":
        # Excel：先确保 SQLite 镜像
        if dsn.db_type == "excel" and conn is not None:
            import asyncio

            params = dsn_to_connect_params(dsn)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 启动路径外由 probe/executor 显式 ensure
                    pass
                else:
                    loop.run_until_complete(conn.ensure_mirror(params))  # type: ignore[attr-defined]
            except Exception:
                pass
        _engine = create_async_engine(url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
        _sync_engine = None
        _sync_session_factory = None
        return _engine

    if mode == "sync":
        _sync_engine = create_engine(url, pool_pre_ping=True)
        _sync_session_factory = sessionmaker(_sync_engine, expire_on_commit=False)
        _engine = None
        _session_factory = None
        return _sync_engine

    # clickhouse_http：不建 SQLAlchemy 引擎
    _engine = None
    _session_factory = None
    _sync_engine = None
    _sync_session_factory = None
    return None


def get_business_engine_mode() -> str:
    get_business_engine()
    return _engine_mode or "async"


async def invalidate_business_engine() -> None:
    """dispose 并清空单例，下次 get_business_engine 按最新 DSN 重建。"""
    global _engine, _session_factory, _sync_engine, _sync_session_factory, _engine_url, _engine_mode
    if _engine is not None:
        await _engine.dispose()
    if _sync_engine is not None:
        _sync_engine.dispose()
    _engine = None
    _session_factory = None
    _sync_engine = None
    _sync_session_factory = None
    _engine_url = None
    _engine_mode = None


def get_business_session_factory() -> async_sessionmaker[AsyncSession]:
    get_business_engine()
    if _session_factory is None:
        raise RuntimeError("当前业务库不支持 AsyncSession（同步或 HTTP 驱动）")
    return _session_factory


async def get_business_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends：业务库只读会话（introspect 等）。"""
    import asyncio

    mode = get_business_engine_mode()
    if mode == "async":
        factory = get_business_session_factory()
        async with factory() as session:
            yield session
        return

    if mode == "sync":
        sync_engine = get_sync_business_engine()
        if sync_engine is None:
            get_business_engine()
            sync_engine = get_sync_business_engine()

        class _SyncAsyncSession:
            """把同步 engine 包装成有限的 async execute，供 introspect 使用。"""

            async def execute(self, statement, params=None):
                def _run():
                    with sync_engine.connect() as conn:
                        result = conn.execute(statement, params or {})
                        # 物化结果，连接关闭后仍可读
                        class _Materialized:
                            def __init__(self, keys, rows):
                                self._keys = keys
                                self._rows = rows

                            def mappings(self):
                                class _M:
                                    def __init__(self, keys, rows):
                                        self._keys = list(keys)
                                        self._rows = rows

                                    def first(self):
                                        return self._rows[0] if self._rows else None

                                    def all(self):
                                        return list(self._rows)

                                mapped = [dict(zip(self._keys, r)) for r in self._rows]
                                return _M(self._keys, mapped)

                            def first(self):
                                return self._rows[0] if self._rows else None

                            def fetchall(self):
                                return list(self._rows)

                            def keys(self):
                                return self._keys

                        return _Materialized(result.keys(), list(result.fetchall()))

                return await asyncio.to_thread(_run)

        yield _SyncAsyncSession()
        return

    if mode == "clickhouse_http":
        dsn = resolve_business_dsn()

        class _ClickhouseHttpSession:
            """clickhouse-connect HTTP 包装，供 Meta introspect 使用。"""

            async def execute(self, statement, params=None):
                def _run():
                    import clickhouse_connect

                    sql = str(statement)
                    # SQLAlchemy TextClause → 去掉 text() 包装痕迹
                    if hasattr(statement, "text"):
                        sql = statement.text
                    bind = dict(params or {})
                    for k, v in bind.items():
                        token = f":{k}"
                        if isinstance(v, str):
                            sql = sql.replace(token, "'" + v.replace("'", "''") + "'")
                        elif v is None:
                            sql = sql.replace(token, "NULL")
                        else:
                            sql = sql.replace(token, str(v))

                    http_port = 8123 if int(dsn.port or 0) in (9000, 0) else int(dsn.port)
                    client = clickhouse_connect.get_client(
                        host=dsn.host,
                        port=http_port,
                        username=dsn.user or "default",
                        password=dsn.password or "",
                        database=dsn.database or "default",
                    )
                    try:
                        result = client.query(sql)
                        keys = list(result.column_names)
                        rows = list(result.result_rows)

                        class _Materialized:
                            def __init__(self, keys, rows):
                                self._keys = keys
                                self._rows = rows

                            def mappings(self):
                                class _M:
                                    def __init__(self, keys, rows):
                                        self._keys = list(keys)
                                        self._rows = rows

                                    def first(self):
                                        return self._rows[0] if self._rows else None

                                    def all(self):
                                        return list(self._rows)

                                mapped = [dict(zip(self._keys, r)) for r in self._rows]
                                return _M(self._keys, mapped)

                            def first(self):
                                return self._rows[0] if self._rows else None

                            def fetchall(self):
                                return list(self._rows)

                            def keys(self):
                                return self._keys

                        return _Materialized(keys, rows)
                    finally:
                        client.close()

                return await asyncio.to_thread(_run)

        yield _ClickhouseHttpSession()
        return

    raise RuntimeError("当前业务库类型不支持 Meta AsyncSession introspect，请使用校验通过的引擎")


async def check_business_connection() -> bool:
    """就绪探针：能否连上业务只读库。"""
    try:
        dsn = resolve_business_dsn()
        conn = registry.get(dsn.db_type)
        if conn is None:
            return False
        result = await conn.probe(dsn_to_connect_params(dsn))
        return result.ok
    except Exception:
        return False


def get_sync_business_engine():
    get_business_engine()
    return _sync_engine
