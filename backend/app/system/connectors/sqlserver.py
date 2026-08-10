"""SQL Server 连接器：优先 aioodbc（async），回退 pymssql（sync probe + 同步 URL 标记）。"""

from __future__ import annotations

import asyncio
from urllib.parse import quote_plus

from app.system.connectors.base import ConnectParams, ProbeResult
from app.system.connectors.version_features import tsql_features


class SqlServerConnector:
    db_type = "sqlserver"
    dialect = "tsql"
    sqlglot_read = "tsql"
    sqlglot_dialect = "tsql"
    display_name = "SQL Server"

    def __init__(self) -> None:
        self.uses_async_engine = self._has_aioodbc()

    @staticmethod
    def _has_aioodbc() -> bool:
        try:
            import aioodbc  # noqa: F401

            return True
        except ImportError:
            return False

    @staticmethod
    def _has_pymssql() -> bool:
        try:
            import pymssql  # noqa: F401

            return True
        except ImportError:
            return False

    def build_sqlalchemy_url(self, params: ConnectParams) -> str:
        user = quote_plus(params.user)
        password = quote_plus(params.password or "")
        if self.uses_async_engine:
            driver = quote_plus(
                str(params.options.get("odbc_driver") or "ODBC Driver 18 for SQL Server")
            )
            return (
                f"mssql+aioodbc://{user}:{password}@{params.host}:{params.port}/{params.database}"
                f"?driver={driver}&TrustServerCertificate=yes"
            )
        # sync pymssql — business 层将走 to_thread
        return (
            f"mssql+pymssql://{user}:{password}@{params.host}:{params.port}/{params.database}"
        )

    async def probe(self, params: ConnectParams) -> ProbeResult:
        if self.uses_async_engine:
            return await self._probe_aioodbc(params)
        if self._has_pymssql():
            return await asyncio.to_thread(self._probe_pymssql, params)
        return ProbeResult(
            ok=False,
            message="未安装 aioodbc 或 pymssql，请 pip install aioodbc 或 pymssql",
        )

    async def _probe_aioodbc(self, params: ConnectParams) -> ProbeResult:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(self.build_sqlalchemy_url(params), pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                ver = await conn.execute(text("SELECT @@VERSION"))
                version = str(ver.scalar() or "")[:120] or None
            return ProbeResult(ok=True, message="连通成功", server_version=version)
        except Exception as e:
            # ODBC 驱动缺失时回退 pymssql
            if self._has_pymssql():
                return await asyncio.to_thread(self._probe_pymssql, params)
            return ProbeResult(ok=False, message=str(e)[:300])
        finally:
            await engine.dispose()

    def _probe_pymssql(self, params: ConnectParams) -> ProbeResult:
        from sqlalchemy import create_engine, text

        url = (
            f"mssql+pymssql://{quote_plus(params.user)}:{quote_plus(params.password or '')}"
            f"@{params.host}:{params.port}/{params.database}"
        )
        engine = create_engine(url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                ver = conn.execute(text("SELECT @@VERSION"))
                version = str(ver.scalar() or "")[:120] or None
            return ProbeResult(ok=True, message="连通成功（pymssql）", server_version=version)
        except Exception as e:
            return ProbeResult(ok=False, message=str(e)[:300])
        finally:
            engine.dispose()

    async def detect_version(self, params: ConnectParams) -> str | None:
        result = await self.probe(params)
        return result.server_version if result.ok else None

    def features_for_version(self, server_version: str | None) -> frozenset[str]:
        return tsql_features(server_version)

    def prompt_dialect_label(self, server_version: str | None) -> str:
        ver = (server_version or "未知版本").split("\n")[0][:60]
        return f"{self.display_name} {ver}（T-SQL；支持 CTE/窗口函数）"
