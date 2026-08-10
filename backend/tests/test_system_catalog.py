"""Catalog / registry 反写死单测。"""

from __future__ import annotations

from app.system.catalog_loader import get_llm_provider, has_llm_provider, list_llm_providers
from app.system.connectors import registry


def test_llm_providers_from_yaml():
    items = list_llm_providers()
    assert len(items) >= 5
    assert has_llm_provider("deepseek")
    assert get_llm_provider("dashscope") is not None


def test_mysql_always_registered():
    assert registry.is_available("mysql")
    assert registry.is_available("doris")
    assert registry.is_available("starrocks")
