"""
Elasticsearch 客户端：问数索引与 bulk 写入。
"""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from config.settings import Settings


class AskElasticsearchClient:
    """问数 ES 索引操作（与 RAGFlow 索引通过前缀隔离）。"""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = AsyncElasticsearch(
            settings.elasticsearch_url,
            request_timeout=60,
        )

    @property
    def index_prefix(self) -> str:
        return self._settings.elasticsearch_index_prefix

    def index_name(self, suffix: str) -> str:
        return f"{self.index_prefix}{suffix}"

    async def close(self) -> None:
        await self._client.close()

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def recreate_vector_index(self, suffix: str, dims: int) -> str:
        """删除并重建带 dense_vector 的索引。"""
        name = self.index_name(suffix)
        if await self._client.indices.exists(index=name):
            await self._client.indices.delete(index=name)
        await self._client.indices.create(
            index=name,
            mappings={
                "properties": {
                    "search_text": {"type": "text"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": dims,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            },
        )
        return name

    async def recreate_value_index(self, suffix: str) -> str:
        """删除并重建字段取值全文索引。"""
        name = self.index_name(suffix)
        if await self._client.indices.exists(index=name):
            await self._client.indices.delete(index=name)
        await self._client.indices.create(
            index=name,
            mappings={
                "properties": {
                    "search_text": {"type": "text"},
                    "table_name": {"type": "keyword"},
                    "column_name": {"type": "keyword"},
                    "value_text": {"type": "keyword"},
                    "display_label": {"type": "text"},
                }
            },
        )
        return name

    async def bulk_index(self, index: str, docs: list[dict]) -> int:
        """bulk 写入文档，返回成功条数。"""
        if not docs:
            return 0

        actions = [{"_index": index, "_source": doc} for doc in docs]
        success, _ = await async_bulk(self._client, actions, refresh=True)
        return int(success)

    async def search_vector(
        self,
        suffix: str,
        query_vector: list[float],
        *,
        top_k: int,
        query_text: str | None = None,
        filter_expr: str | None = None,
    ) -> list[dict]:
        """dense_vector kNN 检索，返回 _source + _score。"""
        index = self.index_name(suffix)
        if not await self._client.indices.exists(index=index):
            return []

        resp = await self._client.search(
            index=index,
            knn={
                "field": "embedding",
                "query_vector": query_vector,
                "k": top_k,
                "num_candidates": max(top_k * 10, top_k),
            },
            size=top_k,
        )
        hits = resp.get("hits", {}).get("hits", [])
        results: list[dict] = []
        for hit in hits:
            src = dict(hit.get("_source") or {})
            src["_score"] = float(hit.get("_score") or 0.0)
            results.append(src)
        return results

    async def search_fulltext(
        self,
        suffix: str,
        query_text: str,
        *,
        top_k: int,
    ) -> list[dict]:
        """全文检索 search_text 字段。"""
        index = self.index_name(suffix)
        if not query_text.strip() or not await self._client.indices.exists(index=index):
            return []

        resp = await self._client.search(
            index=index,
            query={"match": {"search_text": {"query": query_text, "operator": "or"}}},
            size=top_k,
        )
        hits = resp.get("hits", {}).get("hits", [])
        results: list[dict] = []
        for hit in hits:
            src = dict(hit.get("_source") or {})
            src["_score"] = float(hit.get("_score") or 0.0)
            results.append(src)
        return results
