"""
轻量指代消解（P1）：识别「刚才/同上」等并附加 hint。
"""

from __future__ import annotations

import re

from app.memory.models import SessionMemory

_REFERENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"刚才|上一轮|上次"), "last_turn"),
    (re.compile(r"同上|一样|同样"), "same_as_last"),
    (re.compile(r"按刚才的维度|同样维度|相同维度"), "same_dimension"),
    (re.compile(r"再查一次|再来一次"), "repeat_last"),
]


def resolve_references(
    question: str,
    memory: SessionMemory | None,
) -> tuple[str, str | None, bool]:
    """
    规则识别指代并可选附加 hint。

    Returns:
        (resolved_question, reference_hint, matched)
        无指代或无可解析槽位时原问句不变（matched=False）。
    """
    q = (question or "").strip()
    if not q or not memory or memory.skipped or not memory.turns:
        return q, None, False

    last = memory.last_turn
    if last is None:
        return q, None, False

    matched_kind: str | None = None
    for pattern, kind in _REFERENCE_PATTERNS:
        if pattern.search(q):
            matched_kind = kind
            break

    if not matched_kind:
        return q, None, False

    hints: list[str] = []
    if last.question:
        hints.append(f"指代上一轮问句：{last.question[:150]}")
    if last.final_sql:
        sql_one_line = " ".join(last.final_sql.split())[:300]
        hints.append(f"可参考上一轮 SQL 的表与维度：{sql_one_line}")
    if last.tables_used:
        hints.append(f"上一轮涉及表：{last.tables_used}")

    hint = "；".join(hints) if hints else None
    return q, hint, True
