"""
检索类只读工具：指标 / 字段取值 / L1 样例（知识库召回）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.l1_service import candidates_from_rows, is_l1_visible
from app.core.context import UserContext
from app.meta.repository import MetaRepository
from app.retrieval.hybrid import HybridRetriever
from config.settings import Settings


async def search_metrics(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """按问句召回指标定义（ES 向量 / MySQL 关键词降级）。"""
    retriever = HybridRetriever(session, settings)
    try:
        metrics = await retriever.recall_metrics_only(query, keywords or [])
        return {
            "query": query,
            "count": len(metrics),
            "items": [
                {
                    "metric_code": m.metric_code,
                    "metric_name": m.metric_name,
                    "score": round(m.score, 4),
                    "formula_preview": (m.formula_text or "")[:200],
                }
                for m in metrics[:8]
            ],
        }
    finally:
        await retriever.close()


async def search_field_values(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """按问句召回字段枚举取值（依赖 copilot_field_value 索引）。"""
    retriever = HybridRetriever(session, settings)
    try:
        values = await retriever.recall_field_values_only(query, keywords or [])
        return {
            "query": query,
            "count": len(values),
            "items": [
                {
                    "table": v.table_name,
                    "column": v.column_name,
                    "value": v.value_text,
                    "label": v.display_label or v.value_text,
                    "score": round(v.score, 4),
                }
                for v in values[:10]
            ],
        }
    finally:
        await retriever.close()


async def search_sql_examples(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str,
    ctx: UserContext,
) -> dict[str, Any]:
    """按问句召回相似 L1 SQL 样例（知识库软参考）。"""
    retriever = HybridRetriever(session, settings)
    try:
        recalled, _mode = await retriever.recall_sql_examples_only(query)
        repo = MetaRepository(session)
        ids = [item.example_id for item in recalled]
        score_map = {item.example_id: item.score for item in recalled}
        rows = [r for r in await repo.get_sql_examples_by_ids(ids) if is_l1_visible(r, ctx)]
        candidates = candidates_from_rows(rows, scores=score_map)
        return {
            "query": query,
            "count": len(candidates),
            "items": [
                {
                    "id": ex.id,
                    "pattern": ex.question_pattern,
                    "description": ex.description,
                    "score": round(ex.recall_score, 4),
                    "sql_preview": ex.sql_text[:300],
                }
                for ex in candidates[: settings.l1_recall_top_k]
            ],
        }
    finally:
        await retriever.close()
