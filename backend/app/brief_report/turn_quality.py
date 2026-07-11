"""问数轮次是否具备报告纳入价值。"""

from __future__ import annotations

import re
from typing import Any

_EMPTY_ANSWER_RE = re.compile(
    r"^(根据查询结果[，,]?\s*)?共返回\s*0\s*行",
    re.IGNORECASE,
)


def turn_row_count(turn: dict[str, Any]) -> int:
    rc = turn.get("row_count")
    if isinstance(rc, int) and rc >= 0:
        return rc
    rows = turn.get("rows") or []
    return len(rows) if isinstance(rows, list) else 0


def turn_has_chart(turn: dict[str, Any]) -> bool:
    spec = turn.get("chart_spec")
    return isinstance(spec, dict) and bool(spec.get("chart_type") or spec.get("status") == "ready")


def is_empty_answer(answer: str | None) -> bool:
    text = re.sub(r"\s+", " ", (answer or "").strip())
    if not text:
        return True
    return bool(_EMPTY_ANSWER_RE.match(text))


def turn_has_reportable_content(turn: dict[str, Any]) -> bool:
    """有数据行、或有图表，且回答非「0 行」占位文案。"""
    rows = turn_row_count(turn)
    has_chart = turn_has_chart(turn)
    answer = turn.get("answer") or ""
    if rows > 0 or has_chart:
        return not is_empty_answer(answer) or rows > 0 or has_chart
    return False


def turn_skip_reason(turn: dict[str, Any]) -> str | None:
    if turn.get("status") != "success":
        return "未成功"
    if not turn_has_reportable_content(turn):
        return "无有效数据"
    return None
