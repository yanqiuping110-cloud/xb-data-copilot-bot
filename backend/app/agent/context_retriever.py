"""
retrieve_context：从 copilot 库组装术语、指标口径与样例 SQL 摘要。
"""

from __future__ import annotations

import json

from app.ask.example_ranker import format_curated_sql_example_lines, rank_curated_examples_for_prompt
from app.ask.semantic_repository import SemanticRepository
from app.core.context import UserContext
from app.policy.role_policy import build_llm_sql_generation_constraints, build_role_context_header
from app.sql.whitelist import get_allowed_tables
from config.settings import Settings, get_settings


async def build_retrieval_context(
    question: str,
    repo: SemanticRepository,
    ctx: UserContext,
    *,
    settings: Settings | None = None,
) -> str:
    """
    拼接检索上下文文本，供 generate_sql Prompt 使用。

    无数据时仍返回表白名单说明，不阻塞流水线。
    """
    cfg = settings or get_settings()
    metrics = await repo.list_metrics()
    examples = await repo.list_sql_examples()
    allowed = sorted(get_allowed_tables())

    parts: list[str] = [
        build_role_context_header(ctx),
        "",
        "【允许查询的业务表】",
        ", ".join(allowed) or "（未配置，使用默认表）",
        "",
    ]

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

    ranked = rank_curated_examples_for_prompt(
        question,
        ctx,
        examples,
        top_k=cfg.curated_example_top_k,
        min_score=cfg.curated_example_min_score,
        allowed_tables=frozenset(allowed),
    )
    parts.extend(format_curated_sql_example_lines(ranked))

    parts.append("【生成约束】")
    parts.extend(build_llm_sql_generation_constraints(ctx))

    return "\n".join(parts)
