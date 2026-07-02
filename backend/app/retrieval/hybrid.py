"""
混合召回：Zvec/ES 向量+全文混合 + MySQL 关键词降级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.code.index_text import build_indexable_search_text
from app.code.repository import CodeKnowledgeRepository
from app.meta.index_text import (
    build_column_search_text,
    build_field_value_search_text,
    build_metric_search_text,
    build_table_search_text,
)
from app.meta.repository import (
    IndexableColumnRow,
    IndexableFieldValueRow,
    IndexableMetricRow,
    IndexableTableRow,
    MetaRepository,
    parse_alias_json,
)
from app.retrieval.embedding import EmbeddingClient
from app.retrieval.search_index import SearchIndexClient, create_search_index_client
from app.retrieval.zvec_client import build_table_name_filter
from app.retrieval.keyword_extractor import extract_keywords
from config.settings import Settings


@dataclass
class RecalledTable:
    """表级召回结果。"""

    table_id: int
    table_name: str
    search_text: str
    score: float
    recall_mode: str


@dataclass
class RecalledColumn:
    """字段召回结果。"""

    column_id: int
    table_id: int
    table_name: str
    column_name: str
    search_text: str
    score: float
    recall_mode: str


@dataclass
class RecalledMetric:
    """指标召回结果。"""

    metric_id: int
    metric_code: str
    metric_name: str
    search_text: str
    score: float
    recall_mode: str
    relevant_tables: str | None = None
    formula_text: str | None = None


@dataclass
class RecalledFieldValue:
    """字段取值召回结果。"""

    field_value_id: int
    table_name: str
    column_name: str
    value_text: str
    display_label: str | None
    search_text: str
    score: float
    recall_mode: str


@dataclass
class RecalledCodeArtifact:
    """代码 artifact 召回结果（§11.8 · 第 11 周）。"""

    artifact_id: int
    repo_id: int
    title: str
    artifact_type: str
    search_text: str
    score: float
    recall_mode: str
    summary_text: str | None = None
    tables: list[str] = field(default_factory=list)


@dataclass
class HybridRecallResult:
    """多路召回合并结果。"""

    keywords: list[str]
    tables: list[RecalledTable] = field(default_factory=list)
    columns: list[RecalledColumn] = field(default_factory=list)
    metrics: list[RecalledMetric] = field(default_factory=list)
    field_values: list[RecalledFieldValue] = field(default_factory=list)
    code_artifacts: list[RecalledCodeArtifact] = field(default_factory=list)
    recall_mode: str = "hybrid"


def _keyword_score(text: str, keywords: list[str]) -> float:
    """关键词在文本中的命中得分（用于 MySQL 降级）。"""
    if not text or not keywords:
        return 0.0
    lower = text.lower()
    score = 0.0
    for kw in keywords:
        k = kw.lower() if kw.isascii() else kw
        if k in lower:
            score += 2.0 if len(kw) >= 3 else 1.0
    return score


def rank_tables_by_keywords(
    rows: list[IndexableTableRow],
    keywords: list[str],
    *,
    top_k: int,
) -> list[RecalledTable]:
    """内存关键词排序表（ES 不可用时的降级）。"""
    scored: list[tuple[float, IndexableTableRow]] = []
    for row in rows:
        text = build_table_search_text(row)
        score = _keyword_score(text, keywords)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RecalledTable(
            table_id=row.table_id,
            table_name=row.table_name,
            search_text=build_table_search_text(row),
            score=score,
            recall_mode="keyword_fallback",
        )
        for score, row in scored[:top_k]
    ]


def rank_columns_by_keywords(
    rows: list[IndexableColumnRow],
    keywords: list[str],
    *,
    top_k: int,
    table_names: set[str] | None = None,
) -> list[RecalledColumn]:
    """内存关键词排序字段（ES 不可用时的降级）。"""
    scored: list[tuple[float, IndexableColumnRow]] = []
    for row in rows:
        if table_names is not None and row.table_name not in table_names:
            continue
        text = build_column_search_text(row)
        score = _keyword_score(text, keywords)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RecalledColumn(
            column_id=row.column_id,
            table_id=row.table_id,
            table_name=row.table_name,
            column_name=row.column_name,
            search_text=build_column_search_text(row),
            score=score,
            recall_mode="keyword_fallback",
        )
        for score, row in scored[:top_k]
    ]


def rank_metrics_by_keywords(
    rows: list[IndexableMetricRow],
    keywords: list[str],
    *,
    top_k: int,
) -> list[RecalledMetric]:
    """内存关键词排序指标。"""
    scored: list[tuple[float, IndexableMetricRow]] = []
    for row in rows:
        text = build_metric_search_text(row)
        score = _keyword_score(text, keywords)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RecalledMetric(
            metric_id=row.metric_id,
            metric_code=row.metric_code,
            metric_name=row.metric_name,
            search_text=build_metric_search_text(row),
            score=score,
            recall_mode="keyword_fallback",
            relevant_tables=row.relevant_tables,
            formula_text=row.formula_text,
        )
        for score, row in scored[:top_k]
    ]


def rank_field_values_by_keywords(
    rows: list[IndexableFieldValueRow],
    keywords: list[str],
    *,
    top_k: int,
) -> list[RecalledFieldValue]:
    """内存关键词排序字段取值。"""
    scored: list[tuple[float, IndexableFieldValueRow]] = []
    for row in rows:
        text = build_field_value_search_text(row)
        score = _keyword_score(text, keywords)
        aliases = parse_alias_json(row.alias_json)
        for kw in keywords:
            if row.display_label and kw in row.display_label:
                score += 2.0
            if any(kw in a for a in aliases):
                score += 1.5
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RecalledFieldValue(
            field_value_id=row.field_value_id,
            table_name=row.table_name,
            column_name=row.column_name,
            value_text=row.value_text,
            display_label=row.display_label,
            search_text=build_field_value_search_text(row),
            score=score,
            recall_mode="keyword_fallback",
        )
        for score, row in scored[:top_k]
    ]


class HybridRetriever:
    """问句混合召回：向量 + 全文，检索后端不可用时 MySQL 关键词降级。"""

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

    async def close(self) -> None:
        await self._index.close()

    async def _index_available(self) -> bool:
        return await self._index.ping()

    def _vector_recall_mode(self) -> str:
        if self._settings.recall_hybrid_rerank and self._settings.vector_store.lower() != "elasticsearch":
            return "vector_hybrid"
        return "vector"

    async def recall_tables_only(
        self,
        question: str,
        keywords: list[str] | None = None,
    ) -> tuple[list[RecalledTable], str]:
        """表级向量/关键词召回。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        use_index = await self._index_available()
        tables = await self._recall_tables(question, kws, use_index=use_index)
        mode = "keyword_fallback" if tables and tables[0].recall_mode == "keyword_fallback" else "hybrid"
        if not use_index and self._settings.recall_keyword_fallback:
            mode = "keyword_fallback"
        return tables, mode

    async def recall_columns_only(
        self,
        question: str,
        keywords: list[str] | None = None,
        *,
        table_names: list[str] | None = None,
    ) -> tuple[list[RecalledColumn], str]:
        """字段向量/关键词召回；可选限定在候选表内。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        use_index = await self._index_available()
        scope = set(table_names) if table_names else None
        cols = await self._recall_columns(question, kws, use_index=use_index, table_names=scope)
        mode = "keyword_fallback" if cols and cols[0].recall_mode == "keyword_fallback" else "hybrid"
        if not use_index and self._settings.recall_keyword_fallback:
            mode = "keyword_fallback"
        return cols, mode

    async def recall_metrics_only(
        self,
        question: str,
        keywords: list[str] | None = None,
    ) -> list[RecalledMetric]:
        """仅指标召回。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        use_index = await self._index_available()
        return await self._recall_metrics(question, kws, use_index=use_index)

    async def recall_field_values_only(
        self,
        question: str,
        keywords: list[str] | None = None,
    ) -> list[RecalledFieldValue]:
        """仅字段取值召回。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        use_index = await self._index_available()
        return await self._recall_field_values(question, kws, use_index=use_index)

    async def recall_all(self, question: str, keywords: list[str] | None = None) -> HybridRecallResult:
        """执行表/字段/指标/取值召回并返回合并结果。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        tables, _ = await self.recall_tables_only(question, kws)
        table_scope = [t.table_name for t in tables] if tables else None
        columns, recall_mode = await self.recall_columns_only(question, kws, table_names=table_scope)
        metrics = await self.recall_metrics_only(question, kws)
        values = await self.recall_field_values_only(question, kws)

        modes = (
            {t.recall_mode for t in tables}
            | {c.recall_mode for c in columns}
            | {m.recall_mode for m in metrics}
            | {v.recall_mode for v in values}
        )
        if modes == {"keyword_fallback"} or (
            not modes and self._settings.recall_keyword_fallback
        ):
            recall_mode = "keyword_fallback"

        return HybridRecallResult(
            keywords=kws,
            tables=tables,
            columns=columns,
            metrics=metrics,
            field_values=values,
            recall_mode=recall_mode,
        )

    async def _recall_tables(
        self,
        question: str,
        keywords: list[str],
        *,
        use_index: bool,
    ) -> list[RecalledTable]:
        top_k = self._settings.recall_top_k_table
        recall_mode = self._vector_recall_mode()
        if use_index:
            try:
                query_text = " ".join(keywords) or question
                vectors = await self._embedding.embed_texts([query_text])
                if vectors:
                    hits = await self._index.search_vector(
                        "table",
                        vectors[0],
                        top_k=top_k,
                        query_text=query_text,
                    )
                    if hits:
                        return [
                            RecalledTable(
                                table_id=int(h["table_id"]),
                                table_name=str(h["table_name"]),
                                search_text=str(h.get("search_text") or ""),
                                score=float(h.get("_score") or 0.0),
                                recall_mode=recall_mode,
                            )
                            for h in hits
                        ]
            except Exception:
                use_index = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_tables()
        return rank_tables_by_keywords(rows, keywords, top_k=top_k)

    async def _recall_columns(
        self,
        question: str,
        keywords: list[str],
        *,
        use_index: bool,
        table_names: set[str] | None = None,
    ) -> list[RecalledColumn]:
        top_k = self._settings.recall_top_k_column
        recall_mode = self._vector_recall_mode()
        if use_index:
            try:
                query_text = " ".join(keywords) or question
                vectors = await self._embedding.embed_texts([query_text])
                if vectors:
                    filter_expr = build_table_name_filter(table_names)
                    hits = await self._index.search_vector(
                        "column",
                        vectors[0],
                        top_k=top_k,
                        query_text=query_text,
                        filter_expr=filter_expr,
                    )
                    if hits:
                        return [
                            RecalledColumn(
                                column_id=int(h["column_id"]),
                                table_id=int(h["table_id"]),
                                table_name=str(h["table_name"]),
                                column_name=str(h["column_name"]),
                                search_text=str(h.get("search_text") or ""),
                                score=float(h.get("_score") or 0.0),
                                recall_mode=recall_mode,
                            )
                            for h in hits
                        ]
            except Exception:
                use_index = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_columns()
        return rank_columns_by_keywords(rows, keywords, top_k=top_k, table_names=table_names)

    async def _recall_metrics(
        self,
        question: str,
        keywords: list[str],
        *,
        use_index: bool,
    ) -> list[RecalledMetric]:
        top_k = self._settings.recall_top_k_metric
        recall_mode = self._vector_recall_mode()
        if use_index:
            try:
                query_text = " ".join(keywords) or question
                vectors = await self._embedding.embed_texts([query_text])
                if vectors:
                    hits = await self._index.search_vector(
                        "metric",
                        vectors[0],
                        top_k=top_k,
                        query_text=query_text,
                    )
                    if hits:
                        return [
                            RecalledMetric(
                                metric_id=int(h["metric_id"]),
                                metric_code=str(h["metric_code"]),
                                metric_name=str(h["metric_name"]),
                                search_text=str(h.get("search_text") or ""),
                                score=float(h.get("_score") or 0.0),
                                recall_mode=recall_mode,
                                relevant_tables=h.get("relevant_tables"),
                            )
                            for h in hits
                        ]
            except Exception:
                use_index = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_metrics()
        return rank_metrics_by_keywords(rows, keywords, top_k=top_k)

    async def _recall_field_values(
        self,
        question: str,
        keywords: list[str],
        *,
        use_index: bool,
    ) -> list[RecalledFieldValue]:
        top_k = self._settings.recall_top_k_value
        if use_index:
            try:
                query_text = " ".join(keywords) or question
                hits = await self._index.search_fulltext("value", query_text, top_k=top_k)
                if hits:
                    return [
                        RecalledFieldValue(
                            field_value_id=int(h["field_value_id"]),
                            table_name=str(h["table_name"]),
                            column_name=str(h["column_name"]),
                            value_text=str(h["value_text"]),
                            display_label=h.get("display_label"),
                            search_text=str(h.get("search_text") or ""),
                            score=float(h.get("_score") or 0.0),
                            recall_mode="fulltext",
                        )
                        for h in hits
                    ]
            except Exception:
                use_index = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_field_values()
        return rank_field_values_by_keywords(rows, keywords, top_k=top_k)

    async def recall_code_artifacts(
        self,
        question: str,
        keywords: list[str] | None = None,
        *,
        top_k: int | None = None,
    ) -> tuple[list[RecalledCodeArtifact], str]:
        """代码 artifact 向量/关键词召回。"""
        if not self._settings.code_knowledge_enabled:
            return [], "disabled"
        kws = keywords if keywords is not None else extract_keywords(question)
        limit = top_k or self._settings.recall_top_k_code
        code_repo = CodeKnowledgeRepository(self._session)
        use_index = await self._index_available()
        recall_mode = self._vector_recall_mode()
        if use_index:
            try:
                query_text = " ".join(kws) or question
                vectors = await self._embedding.embed_texts([query_text])
                if vectors:
                    hits = await self._index.search_vector(
                        "code_artifact",
                        vectors[0],
                        top_k=limit,
                        query_text=query_text,
                    )
                    if hits:
                        items: list[RecalledCodeArtifact] = []
                        for h in hits:
                            tables_raw = h.get("tables_json") or "[]"
                            try:
                                import json

                                tables = json.loads(tables_raw) if isinstance(tables_raw, str) else tables_raw
                            except Exception:
                                tables = []
                            items.append(
                                RecalledCodeArtifact(
                                    artifact_id=int(h["artifact_id"]),
                                    repo_id=int(h.get("repo_id") or 0),
                                    title=str(h.get("title") or ""),
                                    artifact_type=str(h.get("artifact_type") or ""),
                                    search_text=str(h.get("search_text") or ""),
                                    score=float(h.get("_score") or 0.0),
                                    recall_mode=recall_mode,
                                    summary_text=h.get("summary_text"),
                                    tables=list(tables) if isinstance(tables, list) else [],
                                )
                            )
                        return items, "hybrid"
            except Exception:
                use_index = False

        rows = await code_repo.list_indexable_artifacts()
        scored: list[tuple[float, object]] = []
        for row in rows:
            text = build_indexable_search_text(row)
            score = _keyword_score(text, kws)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        import json

        items = []
        for score, row in scored[:limit]:
            tables: list[str] = []
            if row.tables_json:
                try:
                    tables = json.loads(row.tables_json)
                except json.JSONDecodeError:
                    tables = []
            items.append(
                RecalledCodeArtifact(
                    artifact_id=row.artifact_id,
                    repo_id=row.repo_id,
                    title=row.title,
                    artifact_type=row.artifact_type,
                    search_text=row.search_text,
                    score=score,
                    recall_mode="keyword_fallback",
                    summary_text=row.summary_text,
                    tables=tables if isinstance(tables, list) else [],
                )
            )
        mode = "keyword_fallback" if items else "empty"
        return items, mode
