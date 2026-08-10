"""业务库连接器抽象与连接参数。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ConnectParams:
    host: str
    port: int
    database: str
    user: str
    password: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    message: str
    server_version: str | None = None


class DatasourceConnector(Protocol):
    """多引擎连接器协议；业务代码只依赖 registry，不写 db_type 分支。"""

    db_type: str
    dialect: str
    sqlglot_read: str
    sqlglot_dialect: str

    def build_sqlalchemy_url(self, params: ConnectParams) -> str: ...

    async def probe(self, params: ConnectParams) -> ProbeResult: ...

    async def detect_version(self, params: ConnectParams) -> str | None: ...

    def features_for_version(self, server_version: str | None) -> frozenset[str]: ...

    def prompt_dialect_label(self, server_version: str | None) -> str: ...
