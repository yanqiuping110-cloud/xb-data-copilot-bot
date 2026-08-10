"""PostgreSQL 连接器（可选依赖 asyncpg）。"""

from __future__ import annotations

from urllib.parse import quote_plus

from app.system.connectors.base import ConnectParams, ProbeResult
from app.system.connectors.version_features import postgres_features


class PostgresqlConnector:
    db_type = "postgresql"
    dialect = "postgres"
    sqlglot_read = "postgres"
    sqlglot_dialect = "postgres"
    display_name = "PostgreSQL"

    def build_sqlalchemy_url(self, params: ConnectParams) -> str:
        user = quote_plus(params.user)
        password = quote_plus(params.password or "")
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{params.host}:{params.port}/{params.database}"
        )

    async def probe(self, params: ConnectParams) -> ProbeResult:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        url = self.build_sqlalchemy_url(params)
        engine = create_async_engine(url, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                ver = await conn.execute(text("SHOW server_version"))
                version = str(ver.scalar() or "") or None
            return ProbeResult(ok=True, message="连通成功", server_version=version)
        except Exception as e:
            return ProbeResult(ok=False, message=str(e)[:300])
        finally:
            await engine.dispose()

    async def detect_version(self, params: ConnectParams) -> str | None:
        result = await self.probe(params)
        return result.server_version if result.ok else None

    def features_for_version(self, server_version: str | None) -> frozenset[str]:
        return postgres_features(server_version)

    def prompt_dialect_label(self, server_version: str | None) -> str:
        ver = server_version or "未知版本"
        return f"{self.display_name} {ver}（支持 CTE/窗口函数）"
