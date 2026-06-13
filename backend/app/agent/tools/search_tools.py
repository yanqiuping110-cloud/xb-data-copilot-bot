"""
检索类只读工具：指标 / 字段取值 / L1 样例（复用 HybridRetriever 与 example_ranker）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.example_ranker import rank_curated_examples_for_prompt
from app.ask.semantic_repository import SemanticRepository
from app.core.context import UserContext
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
    """按问句召回字段枚举取值（如 project_id=跳绳）。"""
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
    """按问句召回相似 L1 SQL 样例（软参考，非硬命中）。"""
    sem_repo = SemanticRepository(session)
    examples = await sem_repo.list_sql_examples()
    ranked = rank_curated_examples_for_prompt(
        query,
        ctx,
        examples,
        top_k=settings.curated_example_top_k,
        min_score=0,
    )
    return {
        "query": query,
        "count": len(ranked),
        "items": [
            {
                "id": ex.id,
                "pattern": ex.question_pattern,
                "score": score,
                "sql_preview": (ex.sql_template or "")[:300],
            }
            for ex, score in ranked[:5]
        ],
    }
