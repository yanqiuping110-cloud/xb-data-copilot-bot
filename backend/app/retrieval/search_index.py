"""
问数检索索引工厂：默认 Zvec，可选 Elasticsearch（RAGFlow 栈复用）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from config.settings import Settings


@runtime_checkable
class SearchIndexClient(Protocol):
    """问数混合召回索引客户端协议。"""

    async def close(self) -> None: ...

    async def ping(self) -> bool: ...

    async def recreate_vector_index(self, suffix: str, dims: int) -> str: ...

    async def recreate_value_index(self, suffix: str) -> str: ...

    async def bulk_index(self, index: str, docs: list[dict]) -> int: ...

    async def search_vector(
        self,
        suffix: str,
        query_vector: list[float],
        *,
        top_k: int,
        query_text: str | None = None,
        filter_expr: str | None = None,
    ) -> list[dict]: ...

    async def search_fulltext(
        self,
        suffix: str,
        query_text: str,
        *,
        top_k: int,
    ) -> list[dict]: ...


def create_search_index_client(settings: Settings) -> SearchIndexClient:
    """按 VECTOR_STORE 创建检索后端（默认 zvec）。"""
    store = (settings.vector_store or "zvec").strip().lower()
    if store == "elasticsearch":
        from app.retrieval.es_client import AskElasticsearchClient

        return AskElasticsearchClient(settings)

    from app.retrieval.zvec_client import AskZvecClient

    return AskZvecClient(settings)
