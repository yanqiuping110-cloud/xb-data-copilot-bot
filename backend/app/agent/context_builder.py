"""
多阶段召回后的合并、过滤与 LLM 上下文拼装。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.semantic_repository import CuratedSqlExample, SemanticRepository
from app.core.context import UserContext
from app.meta.effective import effective_description
from app.policy.role_policy import build_llm_sql_generation_constraints, build_role_context_header
from app.meta.repository import MetaRepository, TableMetaRow
from app.retrieval.hybrid import (
    HybridRecallResult,
    RecalledColumn,
    RecalledFieldValue,
    RecalledMetric,
)
from app.sql.whitelist import get_allowed_tables


@dataclass
class MergedRecallContext:
    """合并过滤后的结构化召回上下文。"""

    keywords: list[str]
    recall_mode: str
    columns: list[RecalledColumn] = field(default_factory=list)
    metrics: list[RecalledMetric] = field(default_factory=list)
    field_values: list[RecalledFieldValue] = field(default_factory=list)
    tables: list[TableMetaRow] = field(default_factory=list)
    table_names: list[str] = field(default_factory=list)


def _score_example_relevance(question: str, example: CuratedSqlExample) -> int:
    """简单关键词重叠得分，用于挑选 Top-K 样例放入 Prompt。"""
    q = question
    score = 0
    for token in example.question_pattern.replace("（", " ").replace("）", " ").split():
        if len(token) >= 2 and token in q:
            score += 2
    meta = example.meta
    for kw in meta.get("matchAll", []):
        if kw in q:
            score += 1
    for group in meta.get("matchAllGroups", []):
        if any(k in q for k in group):
            score += 1
    for kw in meta.get("matchAny", []):
        if kw in q:
            score += 1
    return score


def merge_retrieved_info(recall: HybridRecallResult) -> MergedRecallContext:
    """合并三路召回为统一结构（不做过滤）。"""
    return MergedRecallContext(
        keywords=recall.keywords,
        recall_mode=recall.recall_mode,
        columns=list(recall.columns),
        metrics=list(recall.metrics),
        field_values=list(recall.field_values),
    )


def filter_tables(merged: MergedRecallContext, *, top_n: int = 5) -> MergedRecallContext:
    """按字段召回得分聚合候选表，保留 Top-N。"""
    table_scores: dict[str, float] = {}
    for col in merged.columns:
        table_scores[col.table_name] = table_scores.get(col.table_name, 0.0) + col.score
    for metric in merged.metrics:
        if metric.relevant_tables:
            for t in metric.relevant_tables.replace(" ", "").split(","):
                if t:
                    table_scores[t] = table_scores.get(t, 0.0) + metric.score * 0.5
    for fv in merged.field_values:
        table_scores[fv.table_name] = table_scores.get(fv.table_name, 0.0) + fv.score * 0.3

    ranked = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    merged.table_names = [name for name, _ in ranked]
    return merged


def filter_metrics(merged: MergedRecallContext, *, top_n: int = 5) -> MergedRecallContext:
    """保留得分最高的指标。"""
    merged.metrics = sorted(merged.metrics, key=lambda m: m.score, reverse=True)[:top_n]
    return merged


async def enrich_tables_from_mysql(
    merged: MergedRecallContext,
    repo: MetaRepository,
) -> MergedRecallContext:
    """从 MySQL 补全候选表的元数据与关系。"""
    tables: list[TableMetaRow] = []
    for name in merged.table_names:
        row = await repo.find_table_by_name(name)
        if row and row.status == 1:
            tables.append(row)
    merged.tables = tables
    return merged


async def build_llm_context_text(
    question: str,
    merged: MergedRecallContext,
    copilot_session: AsyncSession,
    ctx: UserContext,
    *,
    example_top_k: int = 3,
) -> str:
    """
    将结构化召回结果拼为 generate_sql Prompt 上下文。

    无召回时仍输出表白名单与生成约束。
    """
    meta_repo = MetaRepository(copilot_session)
    sem_repo = SemanticRepository(copilot_session)
    allowed = sorted(get_allowed_tables())

    parts: list[str] = [
        build_role_context_header(ctx),
        "",
        f"【召回模式】{merged.recall_mode}",
        f"【问句关键词】{', '.join(merged.keywords) or '（整句）'}",
        "",
        "【允许查询的业务表】",
        ", ".join(allowed) or "（未配置，使用默认表）",
        "",
    ]

    if merged.tables:
        parts.append("【候选表说明（混合召回）】")
        for table in merged.tables:
            desc = effective_description(table.description_manual, table.table_comment_auto)
            line = f"- {table.table_name}"
            if desc:
                line += f"：{desc}"
            if table.grain:
                line += f"；粒度：{table.grain}"
            line += f"；学校字段：{table.sch_id_column}"
            parts.append(line)
        parts.append("")

        if merged.table_names:
            relations = await meta_repo.list_relations()
            relevant = [
                r
                for r in relations
                if r.status == 1
                and (
                    r.from_table_name in merged.table_names
                    or r.to_table_name in merged.table_names
                )
            ]
            if relevant:
                parts.append("【表关系与 JOIN 提示】")
                for r in relevant[:8]:
                    hint = r.join_hint or f"{r.from_table_name}.{r.from_column} = {r.to_table_name}.{r.to_column}"
                    parts.append(f"- {r.from_table_name} → {r.to_table_name}（{r.relation_type}）：{hint}")
                parts.append("")

    if merged.columns:
        parts.append("【相关字段（召回）】")
        for col in merged.columns[:12]:
            parts.append(f"- {col.table_name}.{col.column_name}：{col.search_text[:120]}")
        parts.append("")

    if merged.metrics:
        parts.append("【相关指标与口径】")
        for m in merged.metrics:
            line = f"- {m.metric_name}（{m.metric_code}）"
            if m.formula_text:
                line += f"；公式：{m.formula_text}"
            if m.relevant_tables:
                line += f"；相关表：{m.relevant_tables}"
            parts.append(line)
        parts.append("")

    if merged.field_values:
        parts.append("【字段取值映射（枚举/别名 → 库内值）】")
        for fv in merged.field_values[:10]:
            label = fv.display_label or fv.value_text
            parts.append(f"- {fv.table_name}.{fv.column_name}：「{label}」→ {fv.value_text}")
        parts.append("")

    examples = await sem_repo.list_sql_examples()
    if examples:
        ranked = sorted(
            examples,
            key=lambda ex: (_score_example_relevance(question, ex), -ex.degrade_priority),
            reverse=True,
        )[:example_top_k]
        parts.append("【相似样例 SQL（仅供参考）】")
        for ex in ranked:
            parts.append(f"问法示例：{ex.question_pattern}")
            parts.append(f"SQL：{ex.sql_text[:500]}")
            parts.append("")

    parts.append("【生成约束】")
    parts.extend(build_llm_sql_generation_constraints(ctx))

    return "\n".join(parts)


def span_detail_from_merged(merged: MergedRecallContext) -> dict:
    """写入 copilot_ask_span 的召回摘要。"""
    return {
        "recall_mode": merged.recall_mode,
        "keywords": merged.keywords,
        "column_count": len(merged.columns),
        "metric_count": len(merged.metrics),
        "value_count": len(merged.field_values),
        "table_names": merged.table_names,
        "columns": [
            {"table": c.table_name, "column": c.column_name, "score": c.score, "mode": c.recall_mode}
            for c in merged.columns[:8]
        ],
        "metrics": [
            {"code": m.metric_code, "score": m.score, "mode": m.recall_mode} for m in merged.metrics[:5]
        ],
        "values": [
            {
                "table": v.table_name,
                "column": v.column_name,
                "value": v.value_text,
                "score": v.score,
            }
            for v in merged.field_values[:5]
        ],
    }
