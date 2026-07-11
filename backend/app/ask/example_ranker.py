"""
L1 样例软参考：按问句与 meta_json 规则打分、过滤、排序后注入 LLM Prompt。

不再走硬命中快路径；仅挑选与当前问句最相关的 Top-K 条样例供模型参考。
"""

from __future__ import annotations

from app.ask.semantic_repository import CuratedSqlExample
from app.core.context import UserContext, UserRole


def example_tables_compatible(
    example: CuratedSqlExample,
    allowed_tables: frozenset[str] | set[str],
) -> bool:
    """
    样例 meta.tables 须全部落在当前表白名单内；未声明 tables 时不做表级过滤。
    """
    if not allowed_tables:
        return True
    meta_tables = example.meta.get("tables")
    if not meta_tables or not isinstance(meta_tables, list):
        return True
    names = {str(t).strip().lower() for t in meta_tables if str(t).strip()}
    if not names:
        return True
    allowed = {t.lower() for t in allowed_tables}
    return names.issubset(allowed)


def meta_rules_fully_match(question: str, meta: dict) -> bool:
    """问句是否满足样例 meta 中的 matchAll / matchAny / matchAllGroups 全部规则。"""
    q = question
    for kw in meta.get("matchAll", []):
        if kw not in q:
            return False
    any_list = meta.get("matchAny", [])
    if any_list and not any(k in q for k in any_list):
        return False
    for group in meta.get("matchAllGroups", []):
        if not isinstance(group, list) or not any(k in q for k in group):
            return False
    if not meta.get("matchAll") and not meta.get("matchAny") and not meta.get("matchAllGroups"):
        pattern = meta.get("questionPattern") or ""
        if pattern and pattern not in q and q not in pattern:
            return False
    return True


def is_example_visible_to_user(example: CuratedSqlExample, ctx: UserContext) -> bool:
    """草稿、未发布、角色不符、学校账户不可见的 admin 样例不参与软参考。"""
    if example.meta.get("draft"):
        return False
    if getattr(example, "review_status", 1) == 0:
        return False
    if example.role_scope and ctx.role.value != example.role_scope:
        return False
    if bool(example.meta.get("adminOnly", False)) and ctx.role == UserRole.SCHOOL:
        return False
    return True


def score_curated_example(question: str, example: CuratedSqlExample) -> int:
    """
    问句与样例的相关性得分（越高越应进入 Prompt）。

    综合考虑问句模式词重叠、meta 关键词命中及规则全匹配加成。
    """
    q = question.strip()
    if not q:
        return 0

    score = 0
    meta = example.meta

    for token in example.question_pattern.replace("（", " ").replace("）", " ").split():
        if len(token) >= 2 and token in q:
            score += 2

    pattern = (meta.get("questionPattern") or example.question_pattern or "").strip()
    if pattern and len(pattern) >= 2 and pattern in q:
        score += 5

    for kw in meta.get("matchAll", []):
        if kw in q:
            score += 4

    for group in meta.get("matchAllGroups", []):
        if isinstance(group, list) and any(k in q for k in group):
            score += 5

    for kw in meta.get("matchAny", []):
        if kw in q:
            score += 3

    if meta_rules_fully_match(q, meta):
        score += 12

    return score


def rank_curated_examples_for_prompt(
    question: str,
    ctx: UserContext,
    examples: list[CuratedSqlExample],
    *,
    top_k: int,
    min_score: int = 1,
    allowed_tables: frozenset[str] | set[str] | None = None,
) -> list[tuple[CuratedSqlExample, int]]:
    """
    过滤并排序样例，返回 (样例, 得分) 列表。

    Args:
        top_k: 注入 Prompt 的最大条数。
        min_score: 低于此得分的样例丢弃；无命中时可设为 0 以兜底展示通用样例。
        allowed_tables: 当前问数表白名单；样例 meta.tables 须为其子集才参与排序。
    """
    if top_k <= 0 or not examples:
        return []

    whitelist = allowed_tables or frozenset()
    scored: list[tuple[CuratedSqlExample, int]] = []
    for ex in examples:
        if not is_example_visible_to_user(ex, ctx):
            continue
        if whitelist and not example_tables_compatible(ex, whitelist):
            continue
        relevance = score_curated_example(question, ex)
        if relevance < min_score:
            continue
        scored.append((ex, relevance))

    scored.sort(key=lambda item: (-item[1], item[0].degrade_priority, item[0].id))
    return scored[:top_k]


def format_curated_sql_example_lines(
    ranked: list[tuple[CuratedSqlExample, int]],
    *,
    sql_max_chars: int = 500,
) -> list[str]:
    """将 L1 样例格式化为 Prompt 段落行。"""
    if not ranked:
        return []
    lines = ["【相似样例 SQL（仅供参考；表/列以当前白名单与候选字段为准，勿照搬）】"]
    for ex, relevance in ranked:
        lines.append(f"问法示例：{ex.question_pattern}（相关度={relevance}）")
        lines.append(f"SQL：{ex.sql_text[:sql_max_chars]}")
        lines.append("")
    return lines
