"""系统配置运行时解析结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.system.connectors import registry
from app.system.connectors.base import ConnectParams


@dataclass(frozen=True)
class ResolvedLlmConfig:
    """生效中的 LLM / Embedding 连接配置。"""

    api_base: str
    api_key: str
    model: str
    timeout_sec: int
    temperature: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
    source: str = "env"  # db | env
    name: str | None = None
    model_id: int | None = None
    provider: str | None = None

    @property
    def embedding_dims(self) -> int | None:
        raw = self.extra.get("embedding_dims")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True)
class ResolvedBusinessDsn:
    """生效中的业务只读库连接。"""

    host: str
    port: int
    user: str
    password: str
    database: str
    db_type: str = "mysql"
    server_version: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    source: str = "env"  # db | env
    name: str | None = None
    datasource_id: int | None = None

    @property
    def sqlalchemy_url(self) -> str:
        conn = registry.get(self.db_type) or registry.require("mysql")
        return conn.build_sqlalchemy_url(
            ConnectParams(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                options=dict(self.options or {}),
            )
        )
