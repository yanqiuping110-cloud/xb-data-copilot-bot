"""
元数据知识库 → 检索索引构建（MetaKnowledgeService）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.code.index_text import build_indexable_search_text
from app.code.repository import CodeKnowledgeRepository
from app.meta.index_text import (
    build_column_search_text,
    build_field_value_search_text,
    build_metric_search_text,
    build_table_search_text,
)
from app.meta.repository import MetaRepository
from app.retrieval.embedding import EmbeddingClient
from app.retrieval.search_index import SearchIndexClient, create_search_index_client
from config.settings import Settings


@dataclass
class RebuildIndexResult:
    """重建索引统计。"""

    tables: int
    columns: int
    metrics: int
    field_values: int
    embedding_dims: int
    code_artifacts: int = 0


class MetaKnowledgeService:
    """MySQL 元数据 → Zvec/ES 向量与全文索引。"""

    def __init__(
        self,
        copilot_session: AsyncSession,
        settings: Settings,
        *,
        embedding: EmbeddingClient | None = None,
        search_index: SearchIndexClient | None = None,
    ):
        self._session = copilot_session
        self._settings = settings
        self._repo = MetaRepository(copilot_session)
        self._embedding = embedding or EmbeddingClient(settings)
        self._index = search_index or create_search_index_client(settings)

    async def ping_search_index(self) -> bool:
        """检索后端就绪探针。"""
        return await self._index.ping()

    async def ping_elasticsearch(self) -> bool:
        """兼容旧调用：等同 ping_search_index。"""
        return await self.ping_search_index()

    async def rebuild_all(self) -> RebuildIndexResult:
        """
        全量重建 table / column / metric 向量索引与 field_value 全文索引。
        索引用 effective 描述与别名拼装的 search_text。
        """
        tables = await self._repo.list_indexable_tables()
        columns = await self._repo.list_indexable_columns()
        metrics = await self._repo.list_indexable_metrics()
        field_values = await self._repo.list_indexable_field_values()

        dims = self._settings.embedding_dims
        table_count = 0
        column_count = 0
        metric_count = 0

        if tables:
            table_texts = [build_table_search_text(t) for t in tables]
            table_vectors = await self._embedding.embed_texts(table_texts)
            dims = self._embedding.dims or len(table_vectors[0])
            table_index = await self._index.recreate_vector_index("table", dims)
            table_docs = [
                {
                    "table_id": t.table_id,
                    "table_name": t.table_name,
                    "table_role": t.table_role,
                    "biz_domain": t.biz_domain,
                    "search_text": text,
                    "embedding": vec,
                }
                for t, text, vec in zip(tables, table_texts, table_vectors, strict=True)
            ]
            table_count = await self._index.bulk_index(table_index, table_docs)

        if columns:
            column_texts = [build_column_search_text(c) for c in columns]
            column_vectors = await self._embedding.embed_texts(column_texts)
            dims = self._embedding.dims or len(column_vectors[0])
            col_index = await self._index.recreate_vector_index("column", dims)
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
            column_count = await self._index.bulk_index(col_index, col_docs)

        if metrics:
            metric_texts = [build_metric_search_text(m) for m in metrics]
            metric_vectors = await self._embedding.embed_texts(metric_texts)
            dims = self._embedding.dims or len(metric_vectors[0])
            metric_index = await self._index.recreate_vector_index("metric", dims)
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
            metric_count = await self._index.bulk_index(metric_index, metric_docs)

        value_index = await self._index.recreate_value_index("value")
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
        value_count = await self._index.bulk_index(value_index, value_docs)

        return RebuildIndexResult(
            tables=table_count,
            columns=column_count,
            metrics=metric_count,
            field_values=value_count,
            embedding_dims=dims,
        )

    async def rebuild_code_index(self) -> int:
        """
        代码 artifact → copilot_ask_code_artifact 向量索引（§11.8 · 第 11 周）。

        无 artifact 时仍重建空索引，避免删库后 Zvec 残留旧向量。
        """
        code_repo = CodeKnowledgeRepository(self._session)
        artifacts = await code_repo.list_indexable_artifacts()
        dims = self._settings.embedding_dims
        if artifacts:
            texts = [build_indexable_search_text(a) for a in artifacts]
            vectors = await self._embedding.embed_texts(texts)
            dims = self._embedding.dims or len(vectors[0])
        index = await self._index.recreate_vector_index("code_artifact", dims)
        if not artifacts:
            return 0
        docs = [
            {
                "artifact_id": a.artifact_id,
                "repo_id": a.repo_id,
                "artifact_type": a.artifact_type,
                "title": a.title,
                "summary_text": a.summary_text,
                "tables_json": a.tables_json,
                "search_text": text,
                "embedding": vec,
            }
            for a, text, vec in zip(artifacts, texts, vectors, strict=True)
        ]
        return await self._index.bulk_index(index, docs)

    async def rebuild_all_with_code(self) -> RebuildIndexResult:
        """元数据 + 代码 artifact 全量重建。"""
        base = await self.rebuild_all()
        code_count = await self.rebuild_code_index()
        return RebuildIndexResult(
            tables=base.tables,
            columns=base.columns,
            metrics=base.metrics,
            field_values=base.field_values,
            embedding_dims=base.embedding_dims,
            code_artifacts=code_count,
        )

    async def close(self) -> None:
        await self._index.close()
