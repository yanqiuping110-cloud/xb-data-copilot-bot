"""LLM 适配器：按 Catalog adapterKey 分发（当前默认 openai_compatible）。"""

from __future__ import annotations

from typing import Any, Protocol

from app.system.catalog_loader import get_llm_provider
from app.system.models import ResolvedLlmConfig


class LlmAdapter(Protocol):
    key: str

    def chat_kwargs(self, cfg: ResolvedLlmConfig) -> dict[str, Any]: ...


class OpenAICompatibleAdapter:
    key = "openai_compatible"

    def chat_kwargs(self, cfg: ResolvedLlmConfig) -> dict[str, Any]:
        return {
            "base_url": cfg.api_base,
            "api_key": cfg.api_key or "ollama",
            "model": cfg.model,
            "temperature": cfg.temperature,
            "timeout": cfg.timeout_sec,
        }


_ADAPTERS: dict[str, LlmAdapter] = {
    OpenAICompatibleAdapter.key: OpenAICompatibleAdapter(),
}


def get_adapter(adapter_key: str | None = None, *, provider_code: str | None = None) -> LlmAdapter:
    key = (adapter_key or "").strip()
    if not key and provider_code:
        meta = get_llm_provider(provider_code)
        if meta:
            key = str(meta.get("adapterKey") or meta.get("adapter_key") or "")
    key = key or OpenAICompatibleAdapter.key
    return _ADAPTERS.get(key) or _ADAPTERS[OpenAICompatibleAdapter.key]


def register_adapter(adapter: LlmAdapter) -> None:
    _ADAPTERS[adapter.key] = adapter
