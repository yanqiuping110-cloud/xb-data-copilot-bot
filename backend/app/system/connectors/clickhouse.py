"""ClickHouse 连接器：探测用 clickhouse-connect；引擎优先 asynch。"""

from __future__ import annotations

import asyncio
from urllib.parse import quote_plus

from app.system.connectors.base import ConnectParams, ProbeResult
from app.system.connectors.version_features import clickhouse_features


class ClickhouseConnector:
    db_type = "clickhouse"
    dialect = "clickhouse"
    sqlglot_read = "clickhouse"
    sqlglot_dialect = "clickhouse"
    display_name = "ClickHouse"

    def __init__(self) -> None:
        self.uses_async_engine = self._has_asynch()

    @staticmethod
    def _has_asynch() -> bool:
        try:
            import asynch  # noqa: F401

            return True
        except ImportError:
            return False

    def build_sqlalchemy_url(self, params: ConnectParams) -> str:
        user = quote_plus(params.user)
        password = quote_plus(params.password or "")
        # HTTP 端口常见 8123；native 9000。options.http_port 可覆盖
        if self.uses_async_engine:
            return (
                f"clickhouse+asynch://{user}:{password}"
                f"@{params.host}:{params.port}/{params.database}"
            )
        # 无 asynch 时仍返回占位 URL；执行走 clickhouse_connect
        http_port = int(params.options.get("http_port") or (8123 if params.port == 9000 else params.port))
        return (
            f"clickhouse+http://{user}:{password}@{params.host}:{http_port}/{params.database}"
        )

    async def probe(self, params: ConnectParams) -> ProbeResult:
        if self.uses_async_engine:
            result = await self._probe_asynch(params)
            if result.ok:
                return result
        return await asyncio.to_thread(self._probe_connect, params)

    async def _probe_asynch(self, params: ConnectParams) -> ProbeResult:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(self.build_sqlalchemy_url(params), pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                ver = await conn.execute(text("SELECT version()"))
                version = str(ver.scalar() or "") or None
            return ProbeResult(ok=True, message="连通成功", server_version=version)
        except Exception as e:
            return ProbeResult(ok=False, message=str(e)[:300])
        finally:
            await engine.dispose()

    def _probe_connect(self, params: ConnectParams) -> ProbeResult:
        try:
            import clickhouse_connect
        except ImportError:
            return ProbeResult(
                ok=False,
                message="未安装 clickhouse-connect / asynch，请 pip install clickhouse-connect",
            )
        http_port = int(
            params.options.get("http_port")
            or (8123 if int(params.port or 0) in (9000, 0) else params.port)
        )
        try:
            client = clickhouse_connect.get_client(
                host=params.host,
                port=http_port,
                username=params.user or "default",
                password=params.password or "",
                database=params.database or "default",
            )
            try:
                ver = str(client.command("SELECT version()") or "") or None
                client.command("SELECT 1")
                return ProbeResult(ok=True, message="连通成功（HTTP）", server_version=ver)
            finally:
                client.close()
        except Exception as e:
            return ProbeResult(ok=False, message=str(e)[:300])

    async def detect_version(self, params: ConnectParams) -> str | None:
        result = await self.probe(params)
        return result.server_version if result.ok else None

    def features_for_version(self, server_version: str | None) -> frozenset[str]:
        return clickhouse_features(server_version)

    def prompt_dialect_label(self, server_version: str | None) -> str:
        ver = server_version or "未知版本"
        return f"{self.display_name} {ver}（支持 CTE/窗口函数）"
