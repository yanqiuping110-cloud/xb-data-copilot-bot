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
