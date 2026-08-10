"""系统配置 Catalog 加载器：LLM 供应商与数据源类型的唯一真相源。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CATALOG_DIR = Path(__file__).resolve().parent / "catalogs"


def _load_yaml(name: str) -> dict[str, Any]:
    path = _CATALOG_DIR / name
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"catalog {name} must be a mapping")
    return data


@lru_cache(maxsize=1)
def _llm_providers_raw() -> tuple[dict[str, Any], ...]:
    items = _load_yaml("llm_providers.yaml").get("providers") or []
    return tuple(items)


@lru_cache(maxsize=1)
def _datasource_types_raw() -> tuple[dict[str, Any], ...]:
    items = _load_yaml("datasource_types.yaml").get("types") or []
    return tuple(items)


def list_llm_providers() -> list[dict[str, Any]]:
    return [dict(p) for p in _llm_providers_raw()]


def get_llm_provider(code: str) -> dict[str, Any] | None:
    key = (code or "").strip().lower()
    for p in _llm_providers_raw():
        if str(p.get("code", "")).lower() == key:
            return dict(p)
    return None


def has_llm_provider(code: str) -> bool:
    return get_llm_provider(code) is not None


def list_datasource_types() -> list[dict[str, Any]]:
    return [dict(t) for t in _datasource_types_raw()]


def get_datasource_type(code: str) -> dict[str, Any] | None:
    key = (code or "").strip().lower()
    for t in _datasource_types_raw():
        if str(t.get("code", "")).lower() == key:
            return dict(t)
    return None


def is_datasource_selectable(code: str) -> bool:
    """Catalog 声明可选且连接器已注册才可选。"""
    meta = get_datasource_type(code)
    if meta is None or not bool(meta.get("selectable")):
        return False
    from app.system.connectors import registry

    return registry.is_available(code)
