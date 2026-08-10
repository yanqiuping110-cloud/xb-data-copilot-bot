"""MySQL 协议族连接器（含 Doris / StarRocks 委托）。"""

from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.system.connectors.base import ConnectParams, ProbeResult
from app.system.connectors.version_features import mysql_family_features


class MysqlFamilyConnector:
    def __init__(
        self,
        *,
        db_type: str,
        display_name: str,
        dialect: str = "mysql",
        sqlglot_read: str = "mysql",
        sqlglot_dialect: str = "mysql",
    ) -> None:
        self.db_type = db_type
        self.display_name = display_name
        self.dialect = dialect
        self.sqlglot_read = sqlglot_read
        self.sqlglot_dialect = sqlglot_dialect

    def build_sqlalchemy_url(self, params: ConnectParams) -> str:
        user = quote_plus(params.user)
        password = quote_plus(params.password or "")
        return (
            f"mysql+aiomysql://{user}:{password}"
            f"@{params.host}:{params.port}/{params.database}?charset=utf8mb4"
        )

    async def probe(self, params: ConnectParams) -> ProbeResult:
        url = self.build_sqlalchemy_url(params)
        engine = create_async_engine(url, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                ver = await conn.execute(text("SELECT VERSION()"))
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
        return mysql_family_features(server_version)

    def prompt_dialect_label(self, server_version: str | None) -> str:
        ver = server_version or "未知版本"
        feats = self.features_for_version(server_version)
        extras = []
        if "cte" in feats:
            extras.append("CTE")
        if "window" in feats:
            extras.append("窗口函数")
        hint = f"（支持 {'/'.join(extras)}）" if extras else "（保守：避免窗口函数与 CTE）"
        return f"{self.display_name} {ver}{hint}"


def mysql_connector() -> MysqlFamilyConnector:
    return MysqlFamilyConnector(db_type="mysql", display_name="MySQL")


def doris_connector() -> MysqlFamilyConnector:
    return MysqlFamilyConnector(db_type="doris", display_name="Apache Doris")


def starrocks_connector() -> MysqlFamilyConnector:
    return MysqlFamilyConnector(db_type="starrocks", display_name="StarRocks")
