"""
retrieve_context：从 copilot 库组装术语、指标口径与样例 SQL 摘要。
"""

from __future__ import annotations

import json

from app.ask.semantic_repository import CuratedSqlExample, MetricDefinition, SemanticRepository
from app.sql.whitelist import get_allowed_tables


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


async def build_retrieval_context(
    question: str,
    repo: SemanticRepository,
    *,
    example_top_k: int = 5,
) -> str:
    """
    拼接检索上下文文本，供 generate_sql Prompt 使用。

    无数据时仍返回表白名单说明，不阻塞流水线。
    """
    metrics = await repo.list_metrics()
    examples = await repo.list_sql_examples()
    allowed = sorted(get_allowed_tables())

    parts: list[str] = ["【允许查询的业务表】", ", ".join(allowed) or "（未配置，使用默认表）", ""]

    if metrics:
        parts.append("【指标与口径】")
        for m in metrics:
            line = f"- {m.metric_name}（{m.metric_code}）"
            if m.description:
                line += f"：{m.description}"
            if m.relevant_tables:
                line += f"；相关表：{m.relevant_tables}"
            if m.alias_json:
                try:
                    aliases = json.loads(m.alias_json)
                    if isinstance(aliases, list) and aliases:
                        line += f"；别名：{', '.join(aliases)}"
                except json.JSONDecodeError:
                    pass
            parts.append(line)
        parts.append("")

    if examples:
        ranked = sorted(
            examples,
            key=lambda ex: (_score_example_relevance(question, ex), -ex.degrade_priority),
            reverse=True,
        )[:example_top_k]
        parts.append("【相似样例 SQL（仅供参考，勿照搬若不符合问句）】")
        for ex in ranked:
            parts.append(f"问法示例：{ex.question_pattern}")
            parts.append(f"SQL：{ex.sql_text[:500]}")
            parts.append("")

    parts.append("【生成约束】")
    parts.append("- 方言：MySQL 5.7，仅单条 SELECT，不要 INSERT/UPDATE/DELETE")
    parts.append("- 只能使用上表白名单中的表")
    parts.append("- 学校账户须在 WHERE 中使用 sch_id = :sch_id（不要写具体数字）")
    parts.append("- 输出仅包含 SQL，不要解释")

    return "\n".join(parts)
