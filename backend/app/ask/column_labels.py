"""
问数结果表头本地化：默认展示中文列名，用户明确要求英文时保留原样。
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.context_builder import MergedRecallContext
from app.retrieval.hybrid import RecalledColumn, RecalledMetric

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 用户明确要求英文表头
_ENGLISH_HEADER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"英文表头|英语表头|表头.{0,6}英文|列名.{0,6}英文|字段名.{0,6}英文"),
    re.compile(r"用英文.{0,6}(表头|列名|字段名|显示|展示)"),
    re.compile(r"(表头|列名|字段名).{0,6}用英文"),
    re.compile(r"english\s+(column|header|field)\s*name", re.I),
    re.compile(r"(column|header|field)\s*names?\s+in\s+english", re.I),
)

# 常见 SQL 别名 → 中文表头
_COMMON_ALIAS_LABELS: dict[str, str] = {
    "year": "年份",
    "month": "月份",
    "day": "日期",
    "date": "日期",
    "week": "周",
    "cnt": "数量",
    "count": "数量",
    "total": "合计",
    "total_count": "总数量",
    "total_people": "总人数",
    "total_person": "总人数",
    "total_students": "总学生数",
    "total_minutes": "总时长(分钟)",
    "total_duration": "总时长",
    "total_sport_value": "总运动量",
    "sport_value": "运动量",
    "people_count": "人数",
    "participant_count": "参与人数",
    "row_count": "行数",
    "sch_id": "学校ID",
    "school_id": "学校ID",
    "class_id": "班级ID",
    "activity_id": "活动ID",
    "people_id": "人员ID",
    "create_time": "创建时间",
    "stat_date": "统计日期",
}

_TOKEN_LABELS: dict[str, str] = {
    "total": "总",
    "people": "人数",
    "person": "人数",
    "student": "学生",
    "count": "数量",
    "cnt": "数量",
    "num": "数量",
    "number": "数量",
    "minute": "分钟",
    "minutes": "分钟",
    "duration": "时长",
    "sport": "运动",
    "value": "值",
    "amount": "金额",
    "name": "名称",
    "time": "时间",
    "create": "创建",
    "avg": "平均",
    "max": "最大",
    "min": "最小",
    "sum": "合计",
    "rate": "比率",
    "ratio": "占比",
    "percent": "百分比",
    "activity": "活动",
    "school": "学校",
    "class": "班级",
    "participant": "参与",
    "distinct": "去重",
}


def wants_english_column_headers(question: str) -> bool:
    """用户是否明确要求英文表头。"""
    q = (question or "").strip()
    if not q:
        return False
    return any(p.search(q) for p in _ENGLISH_HEADER_PATTERNS)


def localize_result_columns(
    columns: list[str] | None,
    *,
    question: str,
    state: dict[str, Any] | None = None,
) -> list[str] | None:
    """将结果列名转为中文展示名；已含中文或用户要求英文时保持原样。"""
    if not columns:
        return columns
    if wants_english_column_headers(question):
        return list(columns)

    label_map = build_column_label_map(columns, state)
    localized: list[str] = []
    used: dict[str, int] = {}
    for col in columns:
        label = label_map.get(col) or col
        if label in used:
            used[label] += 1
            label = f"{label}_{used[label]}"
        else:
            used[label] = 1
        localized.append(label)
    return localized


def build_column_label_map(
    columns: list[str],
    state: dict[str, Any] | None = None,
) -> dict[str, str]:
    """为每个结果列名生成中文展示标签。"""
    state = state or {}
    merged = _get_merged(state)
    meta_map = _meta_label_map(merged)
    sql_map = _sql_alias_label_map(state.get("final_sql") or state.get("raw_sql"))

    result: dict[str, str] = {}
    for col in columns:
        if _CJK_RE.search(col):
            result[col] = col
            continue
        key = col.lower()
        if key in _COMMON_ALIAS_LABELS:
            result[col] = _COMMON_ALIAS_LABELS[key]
            continue
        if col in meta_map:
            result[col] = meta_map[col]
            continue
        if key in meta_map:
            result[col] = meta_map[key]
            continue
        if col in sql_map:
            result[col] = sql_map[col]
            continue
        if key in sql_map:
            result[col] = sql_map[key]
            continue
        token_label = _label_from_tokens(key)
        if token_label:
            result[col] = token_label
    return result


def _get_merged(state: dict[str, Any]) -> MergedRecallContext | None:
    raw = state.get("merged_recall")
    if raw is None:
        return None
    if isinstance(raw, MergedRecallContext):
        return raw
    return None


def _meta_label_map(merged: MergedRecallContext | None) -> dict[str, str]:
    """从召回的指标/字段元数据提取列名映射。"""
    if merged is None:
        return {}

    mapping: dict[str, str] = {}
    for metric in merged.metrics:
        _register_metric_labels(mapping, metric)
    for col in merged.columns:
        _register_column_labels(mapping, col)
    return mapping


def _register_metric_labels(mapping: dict[str, str], metric: RecalledMetric) -> None:
    name = (metric.metric_name or "").strip()
    if not name:
        return
    code = (metric.metric_code or "").strip()
    if code:
        mapping[code] = name
        mapping[code.lower()] = name
    for alias in _aliases_from_search_text(metric.search_text):
        mapping[alias.lower()] = name


def _register_column_labels(mapping: dict[str, str], col: RecalledColumn) -> None:
    label = _chinese_from_search_text(col.search_text)
    if not label:
        return
    column_name = col.column_name
    mapping[column_name] = label
    mapping[column_name.lower()] = label


def _aliases_from_search_text(search_text: str) -> list[str]:
    """从指标索引文本中提取可能的英文别名。"""
    tokens: list[str] = []
    for part in (search_text or "").split():
        if _CJK_RE.search(part) or "." in part:
            continue
        if re.fullmatch(r"[a-zA-Z][\w]*", part):
            tokens.append(part)
    return tokens


def _chinese_from_search_text(search_text: str) -> str | None:
    """从字段/指标索引文本中取第一个中文描述片段。"""
    for part in (search_text or "").split():
        if _CJK_RE.search(part) and "." not in part:
            return part.strip("，。；;")
    match = _CJK_RE.search(search_text or "")
    if match:
        snippet = search_text[match.start() :]
        for sep in (" ", "，", ",", "；", ";", "。"):
            idx = snippet.find(sep)
            if idx > 0:
                snippet = snippet[:idx]
        return snippet.strip()
    return None


def _sql_alias_label_map(sql: str | None) -> dict[str, str]:
    """解析 SELECT 中的 AS 别名，若表达式含中文则用作表头。"""
    if not sql:
        return {}
    mapping: dict[str, str] = {}
    for alias, expr in _parse_select_aliases(sql):
        label = _chinese_from_expression(expr)
        if label:
            mapping[alias] = label
            mapping[alias.lower()] = label
    return mapping


def _parse_select_aliases(sql: str) -> list[tuple[str, str]]:
    """粗略解析 SELECT 列表中的 `expr AS alias`。"""
    upper = sql.upper()
    start = upper.find("SELECT")
    if start < 0:
        return []
    from_idx = upper.find(" FROM ", start)
    if from_idx < 0:
        return []
    select_list = sql[start + 6 : from_idx]
    parts = _split_select_items(select_list)
    pairs: list[tuple[str, str]] = []
    as_re = re.compile(r"\s+AS\s+", re.I)
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        m = as_re.split(piece, maxsplit=1)
        if len(m) == 2:
            pairs.append((m[1].strip().strip("`\"'"), m[0].strip()))
    return pairs


def _split_select_items(select_list: str) -> list[str]:
    """按顶层逗号拆分 SELECT 字段（忽略括号内逗号）。"""
    items: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in select_list:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            items.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        items.append("".join(buf))
    return items


def _chinese_from_expression(expr: str) -> str | None:
    if _CJK_RE.search(expr):
        return _chinese_from_search_text(expr)
    return None


def _label_from_tokens(name: str) -> str | None:
    """将 snake_case 英文别名按词素拼成中文（兜底）。"""
    if _CJK_RE.search(name):
        return None
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return None
    tokens = [t for t in name.split("_") if t]
    if not tokens or not all(t in _TOKEN_LABELS for t in tokens):
        return None
    return "".join(_TOKEN_LABELS[t] for t in tokens)
