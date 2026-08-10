"""当前业务库方言 / 版本上下文（问数 Prompt、sqlglot、guard 唯一来源）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.system.connectors import registry
from app.system.connectors.base import ConnectParams
from app.system.models import ResolvedBusinessDsn
from app.system.runtime_config import resolve_business_dsn
from config.settings import Settings


@dataclass(frozen=True)
class ResolvedSqlContext:
    db_type: str
    dialect: str
    sqlglot_read: str
    sqlglot_dialect: str
    server_version: str | None
    version_major: int | None
    version_minor: int | None
    features: frozenset[str] = field(default_factory=frozenset)
    prompt_dialect_label: str = ""

    @property
    def supports_cte(self) -> bool:
        return "cte" in self.features

    @property
    def supports_window(self) -> bool:
        return "window" in self.features

    def aggregate_strategy_hint(self) -> str:
        if self.supports_cte or self.supports_window:
            return (
                "可用 CTE / 窗口函数做分路聚合；避免无必要的笛卡尔 JOIN 后再 SUM。"
            )
        return (
            "当前库版本对窗口函数/CTE 支持有限：必须以汇聚表为 FROM 主表，"
            "每个来源表的指标用独立标量子查询聚合，禁止多来源表同时 JOIN 再 SUM。"
        )


def _parse_major_minor(server_version: str | None) -> tuple[int | None, int | None]:
    from app.system.connectors.version_features import parse_version_tuple

    if not server_version:
        return None, None
    major, minor = parse_version_tuple(server_version)
    if major == 0 and minor == 0:
        return None, None
    return major, minor


def build_sql_context_from_dsn(dsn: ResolvedBusinessDsn) -> ResolvedSqlContext:
    db_type = (dsn.db_type or "mysql").strip().lower()
    conn = registry.get(db_type)
    if conn is None:
        # 未注册时保守回退到 mysql 语法标签，避免崩链路；探测仍会失败
        from app.system.connectors.mysql import mysql_connector

        conn = mysql_connector()
        db_type = "mysql"
    version = dsn.server_version
    major, minor = _parse_major_minor(version)
    features = conn.features_for_version(version)
    return ResolvedSqlContext(
        db_type=db_type,
        dialect=conn.dialect,
        sqlglot_read=conn.sqlglot_read,
        sqlglot_dialect=conn.sqlglot_dialect,
        server_version=version,
        version_major=major,
        version_minor=minor,
        features=features,
        prompt_dialect_label=conn.prompt_dialect_label(version),
    )


def resolve_sql_context(settings: Settings | None = None) -> ResolvedSqlContext:
    dsn = resolve_business_dsn(settings)
    return build_sql_context_from_dsn(dsn)


def dsn_to_connect_params(dsn: ResolvedBusinessDsn) -> ConnectParams:
    return ConnectParams(
        host=dsn.host,
        port=dsn.port,
        database=dsn.database,
        user=dsn.user,
        password=dsn.password,
        options=dict(dsn.options or {}),
    )
