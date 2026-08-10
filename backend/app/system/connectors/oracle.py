"""Oracle 连接器（oracledb thin；async URL 优先）。"""

from __future__ import annotations

import asyncio
from urllib.parse import quote_plus

from app.system.connectors.base import ConnectParams, ProbeResult
from app.system.connectors.version_features import parse_version_tuple


def oracle_features(server_version: str | None) -> frozenset[str]:
    feats = {"select", "join", "subquery", "group_by", "cte", "window"}
    major, _ = parse_version_tuple(server_version)
    if major >= 12:
        feats |= {"fetch_first"}
    return frozenset(feats)


class OracleConnector:
    db_type = "oracle"
    dialect = "oracle"
    sqlglot_read = "oracle"
    sqlglot_dialect = "oracle"
    display_name = "Oracle"
    uses_async_engine = True

    def build_sqlalchemy_url(self, params: ConnectParams) -> str:
        user = quote_plus(params.user)
        password = quote_plus(params.password or "")
        # service_name 优先；否则 database 当 service / SID
        service = str(params.options.get("service_name") or params.database or "ORCL")
        host = params.host
        port = params.port or 1521
        # SQLAlchemy 2 + oracledb async
        return f"oracle+oracledb_async://{user}:{password}@{host}:{port}/?service_name={quote_plus(service)}"

    def build_sync_url(self, params: ConnectParams) -> str:
        user = quote_plus(params.user)
        password = quote_plus(params.password or "")
        service = str(params.options.get("service_name") or params.database or "ORCL")
        return (
            f"oracle+oracledb://{user}:{password}@{params.host}:{params.port}/?service_name={quote_plus(service)}"
        )

    async def probe(self, params: ConnectParams) -> ProbeResult:
        try:
            import oracledb  # noqa: F401
        except ImportError:
            return ProbeResult(
                ok=False,
                message="未安装 oracledb，请 pip install oracledb",
            )

        # 优先 async engine；失败再 thin sync
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(self.build_sqlalchemy_url(params), pool_pre_ping=True)
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1 FROM DUAL"))
                    ver = await conn.execute(
                        text("SELECT BANNER FROM v$version WHERE ROWNUM = 1")
                    )
                    version = str(ver.scalar() or "")[:120] or None
                return ProbeResult(ok=True, message="连通成功", server_version=version)
            finally:
                await engine.dispose()
        except Exception:
            return await asyncio.to_thread(self._probe_sync, params)

    def _probe_sync(self, params: ConnectParams) -> ProbeResult:
        from sqlalchemy import create_engine, text

        engine = create_engine(self.build_sync_url(params), pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM DUAL"))
                ver = conn.execute(text("SELECT BANNER FROM v$version WHERE ROWNUM = 1"))
                version = str(ver.scalar() or "")[:120] or None
            return ProbeResult(ok=True, message="连通成功", server_version=version)
        except Exception as e:
            return ProbeResult(ok=False, message=str(e)[:300])
        finally:
            engine.dispose()

    async def detect_version(self, params: ConnectParams) -> str | None:
        result = await self.probe(params)
        return result.server_version if result.ok else None

    def features_for_version(self, server_version: str | None) -> frozenset[str]:
        return oracle_features(server_version)

    def prompt_dialect_label(self, server_version: str | None) -> str:
        ver = (server_version or "未知版本").split("\n")[0][:60]
        return f"{self.display_name} {ver}（Oracle SQL；LIMIT 用 FETCH FIRST）"
