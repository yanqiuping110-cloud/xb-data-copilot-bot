"""
轻量指代消解（P1）：识别「刚才/同上」等，改写问句并附加 hint。
"""

from __future__ import annotations

import re

from app.memory.models import SessionMemory

_REFERENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"再查一次|再来一次"), "repeat_last"),
    (re.compile(r"同上|一样|同样"), "same_as_last"),
    (re.compile(r"按刚才的维度|同样维度|相同维度|刚才的维度"), "same_dimension"),
    (re.compile(r"刚才|上一轮|上次"), "last_turn"),
]

# 问句中常见时间范围词（按长度降序，避免「最近7天」被「最近」误匹配）
_TIME_TERMS: tuple[str, ...] = (
    "最近30天",
    "最近7天",
    "最近一年",
    "本月",
    "上月",
    "本周",
    "上周",
    "昨日",
    "今日",
)

_TIME_IN_QUESTION_RE = re.compile(
    r"(?:查|看|换成|改为|换为)?(" + "|".join(re.escape(t) for t in _TIME_TERMS) + r")"
)

_PROJECT_FILTER_RE = re.compile(
    r"(?:但不要|只要|只看|限定|仅要)([\u4e00-\u9fff]{2,8})"
)

_REFERENCE_NOISE_RE = re.compile(
    r"按刚才的维度|同样维度|相同维度|刚才的维度|"
    r"同上|一样|同样|再查一次|再来一次|"
    r"刚才|上一轮|上次|[，,、；;]"
)


def _extract_time_term(question: str) -> str | None:
    """从当前问句提取目标时间范围。"""
    match = _TIME_IN_QUESTION_RE.search(question)
    if match:
        return match.group(1)
    for term in _TIME_TERMS:
        if term in question:
            return term
    return None


def _replace_time_in_question(base: str, new_time: str) -> str:
    """将上一轮问句中的时间范围替换为新时间。"""
    for old in _TIME_TERMS:
        if old in base:
            return base.replace(old, new_time, 1)
    # 上一轮无显式时间：在句首或「本校/全平台」后插入
    for prefix in ("本校", "全平台", "平台"):
        if prefix in base:
            idx = base.index(prefix) + len(prefix)
            return base[:idx] + new_time + base[idx:]
    return f"{new_time}{base}"


def _add_project_filter(base: str, project: str) -> str:
    """在指标描述前注入问句中的项目/维度过滤词。"""
    if project in base:
        return base
    for anchor in ("参与人数趋势", "参与人数", "参与人次", "人数趋势", "趋势", "人数", "人次"):
        if anchor in base:
            return base.replace(anchor, f"{project}{anchor}", 1)
    return f"{base}（{project}）"


def _rewrite_reference_question(current: str, last_question: str, kind: str) -> str | None:
    """根据指代类型与当前问句修饰语，改写为可独立执行的问句。"""
    if kind == "repeat_last":
        return last_question

    rewritten = last_question
    new_time = _extract_time_term(current)
    if new_time:
        rewritten = _replace_time_in_question(rewritten, new_time)

    project = _PROJECT_FILTER_RE.search(current)
    if project:
        rewritten = _add_project_filter(rewritten, project.group(1))

    if rewritten != last_question:
        return rewritten

    stripped = _REFERENCE_NOISE_RE.sub("", current).strip()
    if kind in ("same_dimension", "same_as_last", "last_turn") and len(stripped) <= 6:
        return last_question
    return None


def resolve_references(
    question: str,
    memory: SessionMemory | None,
) -> tuple[str, str | None, bool]:
    """
    规则识别指代并改写问句。

    Returns:
        (resolved_question, reference_hint, matched)
        无指代或无可解析槽位时原问句不变（matched=False）。
    """
    q = (question or "").strip()
    if not q or not memory or memory.skipped or not memory.turns:
        return q, None, False

    last = memory.last_turn
    if last is None or not last.question:
        return q, None, False

    matched_kind: str | None = None
    for pattern, kind in _REFERENCE_PATTERNS:
        if pattern.search(q):
            matched_kind = kind
            break

    if not matched_kind:
        return q, None, False

    hints: list[str] = []
    hints.append(f"指代上一轮问句：{last.question[:150]}")
    if last.final_sql:
        sql_one_line = " ".join(last.final_sql.split())[:300]
        hints.append(f"可参考上一轮 SQL 的表与维度：{sql_one_line}")
    if last.tables_used:
        hints.append(f"上一轮涉及表：{last.tables_used}")

    rewritten = _rewrite_reference_question(q, last.question, matched_kind)
    resolved = rewritten if rewritten else q
    if rewritten and rewritten != q:
        hints.append(f"改写后问句：{rewritten[:150]}")

    hint = "；".join(hints) if hints else None
    return resolved, hint, True
