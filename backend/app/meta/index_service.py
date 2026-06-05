"""
元数据知识库 → Elasticsearch 索引构建（MetaKnowledgeService）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.index_text import (
    build_column_search_text,
    build_field_value_search_text,
    build_metric_search_text,
)
from app.meta.repository import MetaRepository
from app.retrieval.embedding import EmbeddingClient
from app.retrieval.es_client import AskElasticsearchClient
from config.settings import Settings


@dataclass
class RebuildIndexResult:
    """重建索引统计。"""

    columns: int
    metrics: int
    field_values: int
    embedding_dims: int


class MetaKnowledgeService:
    """MySQL 元数据 → ES 向量/全文索引。"""

    def __init__(
        self,
        copilot_session: AsyncSession,
        settings: Settings,
        *,
        embedding: EmbeddingClient | None = None,
        es: AskElasticsearchClient | None = None,
    ):
        self._session = copilot_session
        self._settings = settings
        self._repo = MetaRepository(copilot_session)
        self._embedding = embedding or EmbeddingClient(settings)
        self._es = es or AskElasticsearchClient(settings)

    async def ping_elasticsearch(self) -> bool:
        """ES 就绪探针。"""
        return await self._es.ping()

    async def rebuild_all(self) -> RebuildIndexResult:
        """
        全量重建 column / metric 向量索引与 field_value 全文索引。
        索引用 effective 描述与别名拼装的 search_text。
        """
        columns = await self._repo.list_indexable_columns()
        metrics = await self._repo.list_indexable_metrics()
        field_values = await self._repo.list_indexable_field_values()

        dims = self._settings.embedding_dims
        column_count = 0
        metric_count = 0

        if columns:
            column_texts = [build_column_search_text(c) for c in columns]
            column_vectors = await self._embedding.embed_texts(column_texts)
            dims = self._embedding.dims or len(column_vectors[0])
            col_index = await self._es.recreate_vector_index("column", dims)
            col_docs = [
                {
                    "column_id": c.column_id,
                    "table_id": c.table_id,
                    "table_name": c.table_name,
                    "column_name": c.column_name,
                    "column_role": c.column_role,
                    "search_text": text,
                    "embedding": vec,
                }
                for c, text, vec in zip(columns, column_texts, column_vectors, strict=True)
            ]
            column_count = await self._es.bulk_index(col_index, col_docs)

        if metrics:
            metric_texts = [build_metric_search_text(m) for m in metrics]
            metric_vectors = await self._embedding.embed_texts(metric_texts)
            dims = self._embedding.dims or len(metric_vectors[0])
            metric_index = await self._es.recreate_vector_index("metric", dims)
            metric_docs = [
                {
                    "metric_id": m.metric_id,
                    "metric_code": m.metric_code,
                    "metric_name": m.metric_name,
                    "relevant_tables": m.relevant_tables,
                    "search_text": text,
                    "embedding": vec,
                }
                for m, text, vec in zip(metrics, metric_texts, metric_vectors, strict=True)
            ]
            metric_count = await self._es.bulk_index(metric_index, metric_docs)

        value_index = await self._es.recreate_value_index("value")
        value_docs = [
            {
                "field_value_id": v.field_value_id,
                "column_id": v.column_id,
                "table_name": v.table_name,
                "column_name": v.column_name,
                "value_text": v.value_text,
                "display_label": v.display_label,
                "search_text": build_field_value_search_text(v),
            }
            for v in field_values
        ]
        value_count = await self._es.bulk_index(value_index, value_docs)

        return RebuildIndexResult(
            columns=column_count,
            metrics=metric_count,
            field_values=value_count,
            embedding_dims=dims,
        )

    async def close(self) -> None:
        await self._es.close()
