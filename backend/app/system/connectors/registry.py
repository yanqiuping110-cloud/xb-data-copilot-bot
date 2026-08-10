"""数据源连接器注册表：按 db_type 分发，禁止业务层白名单 if。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.system.connectors.base import DatasourceConnector

_REGISTRY: dict[str, DatasourceConnector] = {}
_UNAVAILABLE: dict[str, str] = {}


def register(connector: DatasourceConnector) -> None:
    _REGISTRY[connector.db_type] = connector
    _UNAVAILABLE.pop(connector.db_type, None)


def mark_unavailable(db_type: str, reason: str) -> None:
    _UNAVAILABLE[db_type] = reason
    _REGISTRY.pop(db_type, None)


def get(db_type: str) -> DatasourceConnector | None:
    return _REGISTRY.get((db_type or "").strip().lower())


def require(db_type: str) -> DatasourceConnector:
    conn = get(db_type)
    if conn is not None:
        return conn
    reason = _UNAVAILABLE.get((db_type or "").strip().lower())
    if reason:
        raise LookupError(reason)
    raise LookupError(f"未注册的数据源类型：{db_type}")


def available_types() -> list[str]:
    return sorted(_REGISTRY.keys())


def is_available(db_type: str) -> bool:
    return get(db_type) is not None


def unavailable_reason(db_type: str) -> str | None:
    return _UNAVAILABLE.get((db_type or "").strip().lower())
