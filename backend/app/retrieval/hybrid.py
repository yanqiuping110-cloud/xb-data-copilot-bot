"""
混合召回：ES 向量/全文 + MySQL 关键词降级。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.retrieval.es_client import AskElasticsearchClient
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
class HybridRecallResult:
    """多路召回合并结果。"""

    keywords: list[str]
    tables: list[RecalledTable] = field(default_factory=list)
    columns: list[RecalledColumn] = field(default_factory=list)
    metrics: list[RecalledMetric] = field(default_factory=list)
    field_values: list[RecalledFieldValue] = field(default_factory=list)
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
    """问句混合召回：向量 + 全文，ES 故障时 MySQL 关键词降级。"""

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

    async def close(self) -> None:
        await self._es.close()

    async def _es_available(self) -> bool:
        return await self._es.ping()

    async def recall_tables_only(
        self,
        question: str,
        keywords: list[str] | None = None,
    ) -> tuple[list[RecalledTable], str]:
        """表级向量/关键词召回。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        use_es = await self._es_available()
        tables = await self._recall_tables(question, kws, use_es=use_es)
        mode = "keyword_fallback" if tables and tables[0].recall_mode == "keyword_fallback" else "hybrid"
        if not use_es and self._settings.recall_keyword_fallback:
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
        use_es = await self._es_available()
        scope = set(table_names) if table_names else None
        cols = await self._recall_columns(question, kws, use_es=use_es, table_names=scope)
        mode = "keyword_fallback" if cols and cols[0].recall_mode == "keyword_fallback" else "hybrid"
        if not use_es and self._settings.recall_keyword_fallback:
            mode = "keyword_fallback"
        return cols, mode

    async def recall_metrics_only(
        self,
        question: str,
        keywords: list[str] | None = None,
    ) -> list[RecalledMetric]:
        """仅指标召回。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        use_es = await self._es_available()
        return await self._recall_metrics(question, kws, use_es=use_es)

    async def recall_field_values_only(
        self,
        question: str,
        keywords: list[str] | None = None,
    ) -> list[RecalledFieldValue]:
        """仅字段取值召回。"""
        kws = keywords if keywords is not None else extract_keywords(question)
        use_es = await self._es_available()
        return await self._recall_field_values(question, kws, use_es=use_es)

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
        use_es: bool,
    ) -> list[RecalledTable]:
        top_k = self._settings.recall_top_k_table
        if use_es:
            try:
                query_text = " ".join(keywords) or question
                vectors = await self._embedding.embed_texts([query_text])
                if vectors:
                    hits = await self._es.search_vector("table", vectors[0], top_k=top_k)
                    if hits:
                        return [
                            RecalledTable(
                                table_id=int(h["table_id"]),
                                table_name=str(h["table_name"]),
                                search_text=str(h.get("search_text") or ""),
                                score=float(h.get("_score") or 0.0),
                                recall_mode="es_vector",
                            )
                            for h in hits
                        ]
            except Exception:
                use_es = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_tables()
        return rank_tables_by_keywords(rows, keywords, top_k=top_k)

    async def _recall_columns(
        self,
        question: str,
        keywords: list[str],
        *,
        use_es: bool,
        table_names: set[str] | None = None,
    ) -> list[RecalledColumn]:
        top_k = self._settings.recall_top_k_column
        if use_es:
            try:
                query_text = " ".join(keywords) or question
                vectors = await self._embedding.embed_texts([query_text])
                if vectors:
                    fetch_k = top_k * 3 if table_names else top_k
                    hits = await self._es.search_vector("column", vectors[0], top_k=fetch_k)
                    if hits:
                        results: list[RecalledColumn] = []
                        for h in hits:
                            table_name = str(h["table_name"])
                            if table_names is not None and table_name not in table_names:
                                continue
                            results.append(
                                RecalledColumn(
                                    column_id=int(h["column_id"]),
                                    table_id=int(h["table_id"]),
                                    table_name=table_name,
                                    column_name=str(h["column_name"]),
                                    search_text=str(h.get("search_text") or ""),
                                    score=float(h.get("_score") or 0.0),
                                    recall_mode="es_vector",
                                )
                            )
                            if len(results) >= top_k:
                                break
                        if results:
                            return results
            except Exception:
                use_es = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_columns()
        return rank_columns_by_keywords(rows, keywords, top_k=top_k, table_names=table_names)

    async def _recall_metrics(
        self,
        question: str,
        keywords: list[str],
        *,
        use_es: bool,
    ) -> list[RecalledMetric]:
        top_k = self._settings.recall_top_k_metric
        if use_es:
            try:
                query_text = " ".join(keywords) or question
                vectors = await self._embedding.embed_texts([query_text])
                if vectors:
                    hits = await self._es.search_vector("metric", vectors[0], top_k=top_k)
                    if hits:
                        return [
                            RecalledMetric(
                                metric_id=int(h["metric_id"]),
                                metric_code=str(h["metric_code"]),
                                metric_name=str(h["metric_name"]),
                                search_text=str(h.get("search_text") or ""),
                                score=float(h.get("_score") or 0.0),
                                recall_mode="es_vector",
                                relevant_tables=h.get("relevant_tables"),
                            )
                            for h in hits
                        ]
            except Exception:
                use_es = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_metrics()
        return rank_metrics_by_keywords(rows, keywords, top_k=top_k)

    async def _recall_field_values(
        self,
        question: str,
        keywords: list[str],
        *,
        use_es: bool,
    ) -> list[RecalledFieldValue]:
        top_k = self._settings.recall_top_k_value
        if use_es:
            try:
                query_text = " ".join(keywords) or question
                hits = await self._es.search_fulltext("value", query_text, top_k=top_k)
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
                            recall_mode="es_fulltext",
                        )
                        for h in hits
                    ]
            except Exception:
                use_es = False

        if not self._settings.recall_keyword_fallback:
            return []

        rows = await self._repo.list_indexable_field_values()
        return rank_field_values_by_keywords(rows, keywords, top_k=top_k)
