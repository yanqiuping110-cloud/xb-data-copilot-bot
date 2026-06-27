"""
查询结果 → 图表规格（规则引擎，Fail-closed 图表、Fail-open 问数）。
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.result_assembler import _is_numeric
from app.schemas.chart import ChartSeriesSpec, ChartSpec

_MAX_CHART_ROWS = 500
_PIE_MAX_CATEGORIES = 8
_BAR_MAX_CATEGORIES = 30
_TOP_N_BAR = 20

_TIME_NAME_HINTS = (
    "日期",
    "date",
    "day",
    "time",
    "month",
    "week",
    "year",
    "年",
    "月",
    "日",
    "dt",
)
_ID_NAME_HINTS = ("_id", "sch_id", "activity_id", "user_id", "pk")
_DATE_VALUE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")

_TREND_KEYWORDS = ("趋势", "走势", "每日", "按月", "按周", "曲线", "变化", "daily", "trend")
_COMPARE_KEYWORDS = ("对比", "排名", "top", "各项目", "各部门", "分别", "compare", "rank")
_PIE_KEYWORDS = ("占比", "构成", "份额", "比例", "percent", "proportion")
_DETAIL_KEYWORDS = ("明细", "列表", "导出", "每条", "detail", "list")
_EXPLICIT_CHART_KEYWORDS = ("图表", "图展示", "可视化", "chart", "graph")


def infer_visualization_from_question(question: str) -> dict[str, Any]:
    """问句规则推断 visualization 意图（plan 快路径 / fallback 兜底）。"""
    q = (question or "").strip()
    lower = q.lower()

    if any(k in q or k in lower for k in _DETAIL_KEYWORDS):
        return {
            "enabled": False,
            "user_explicit": False,
            "preferred_types": ["none"],
            "reason": "问句要求明细列表，适合表格展示",
            "fallback_to_table": True,
        }

    user_explicit = any(k in q or k in lower for k in _EXPLICIT_CHART_KEYWORDS)

    if any(k in q or k in lower for k in _PIE_KEYWORDS):
        return {
            "enabled": True,
            "user_explicit": user_explicit,
            "preferred_types": ["pie", "bar"],
            "reason": "问句含占比/构成语义",
            "fallback_to_table": True,
        }

    if any(k in q or k in lower for k in _TREND_KEYWORDS):
        return {
            "enabled": True,
            "user_explicit": user_explicit,
            "preferred_types": ["line", "area"],
            "reason": "问句含趋势/时间序列语义",
            "fallback_to_table": True,
        }

    if any(k in q or k in lower for k in _COMPARE_KEYWORDS):
        return {
            "enabled": True,
            "user_explicit": user_explicit,
            "preferred_types": ["bar", "column"],
            "reason": "问句含对比/排名语义",
            "fallback_to_table": True,
        }

    if user_explicit:
        return {
            "enabled": True,
            "user_explicit": True,
            "preferred_types": ["bar", "line", "pie"],
            "reason": "用户明确要求图表展示",
            "fallback_to_table": True,
        }

    return {
        "enabled": True,
        "user_explicit": False,
        "preferred_types": ["bar", "line", "pie"],
        "reason": "默认尝试在数据适合时生成图表",
        "fallback_to_table": True,
    }


def normalize_visualization_intent(raw: Any) -> dict[str, Any]:
    """规范化 plan 中的 visualization 块。"""
    if not isinstance(raw, dict):
        return infer_visualization_from_question("")
    preferred = raw.get("preferred_types") or raw.get("preferredTypes") or []
    if not isinstance(preferred, list):
        preferred = []
    preferred = [str(p).strip().lower() for p in preferred if str(p).strip()]
    if not preferred:
        preferred = ["bar", "line"]
    return {
        "enabled": bool(raw.get("enabled", True)),
        "user_explicit": bool(raw.get("user_explicit", raw.get("userExplicit", False))),
        "preferred_types": preferred,
        "reason": str(raw.get("reason") or "").strip() or None,
        "fallback_to_table": bool(raw.get("fallback_to_table", raw.get("fallbackToTable", True))),
    }


def _col_values(rows: list[list], col_idx: int) -> list[Any]:
    out: list[Any] = []
    for row in rows:
        if col_idx < len(row):
            out.append(row[col_idx])
    return out


def _is_id_column(name: str) -> bool:
    lower = name.lower()
    if lower in ("id",):
        return True
    return any(h in lower for h in _ID_NAME_HINTS)


def _is_time_column(name: str, rows: list[list], col_idx: int) -> bool:
    lower = name.lower()
    if any(h in lower or h in name for h in _TIME_NAME_HINTS):
        return True
    sample = _col_values(rows, col_idx)[:5]
    if not sample:
        return False
    date_like = sum(1 for v in sample if v is not None and _DATE_VALUE_RE.match(str(v).strip()))
    return date_like >= max(1, len(sample) // 2)


def _is_measure_column(name: str, rows: list[list], col_idx: int) -> bool:
    if _is_id_column(name):
        return False
    values = _col_values(rows, col_idx)
    numeric = sum(1 for v in values if _is_numeric(v))
    return numeric > 0 and numeric >= max(1, len(values) // 3)


def _unique_count(rows: list[list], col_idx: int) -> int:
    seen: set[Any] = set()
    for row in rows:
        if col_idx < len(row):
            seen.add(row[col_idx])
    return len(seen)


def _pick_dimension(columns: list[str], rows: list[list], measures: list[str]) -> str | None:
    measure_set = set(measures)
    time_cols = [
        c for c in columns if c not in measure_set and _is_time_column(c, rows, columns.index(c))
    ]
    if time_cols:
        return time_cols[0]
    cat_cols = [
        c
        for c in columns
        if c not in measure_set and not _is_id_column(c) and not _is_measure_column(c, rows, columns.index(c))
    ]
    if cat_cols:
        return cat_cols[0]
    non_measure = [c for c in columns if c not in measure_set and not _is_id_column(c)]
    return non_measure[0] if non_measure else None


def _compatible(chart_type: str, dim: str | None, measures: list[str], rows: list[list], columns: list[str]) -> bool:
    if not measures or not rows:
        return False
    if chart_type in ("line", "area"):
        if len(rows) < 2:
            return False
        if dim is None:
            return False
        dim_idx = columns.index(dim)
        return _is_time_column(dim, rows, dim_idx) or _unique_count(rows, dim_idx) >= 2
    if chart_type in ("bar", "column"):
        if dim is None:
            return len(measures) >= 1 and len(rows) >= 2
        dim_idx = columns.index(dim)
        n = _unique_count(rows, dim_idx)
        return 2 <= n <= _BAR_MAX_CATEGORIES
    if chart_type == "pie":
        if len(measures) != 1 or dim is None:
            return False
        dim_idx = columns.index(dim)
        n = _unique_count(rows, dim_idx)
        return 2 <= n <= _PIE_MAX_CATEGORIES
    if chart_type == "scatter":
        return len(measures) >= 2 and len(rows) >= 5
    if chart_type == "combo":
        return dim is not None and len(measures) >= 2 and len(rows) >= 2
    return False


def _choose_chart_type(
    preferred: list[str],
    dim: str | None,
    measures: list[str],
    rows: list[list],
    columns: list[str],
    assembly_mode: str | None,
) -> str:
    if assembly_mode == "join_by_date" and dim and len(measures) >= 1:
        if "line" in preferred or not preferred:
            return "line"
        return "line"

    for pt in preferred:
        if pt in ("none",):
            continue
        if pt == "column":
            pt = "bar"
        if pt == "area" and _compatible("line", dim, measures, rows, columns):
            return "area"
        if _compatible(pt, dim, measures, rows, columns):
            return pt

    if dim and _is_time_column(dim, rows, columns.index(dim)) and len(rows) >= 2:
        return "line"
    if dim and len(measures) == 1:
        dim_idx = columns.index(dim)
        n = _unique_count(rows, dim_idx)
        if 2 <= n <= _PIE_MAX_CATEGORIES:
            return "pie"
    if len(measures) >= 2 and dim:
        return "combo" if _compatible("combo", dim, measures, rows, columns) else "bar"
    if dim and len(measures) >= 1:
        return "bar"
    if len(measures) >= 2:
        return "scatter"
    return "none"


def _build_series(chart_type: str, measures: list[str]) -> list[ChartSeriesSpec]:
    if chart_type == "combo":
        types = ["bar", "line"]
        return [
            ChartSeriesSpec(
                name=m,
                column=m,
                type=types[i % len(types)],
            )
            for i, m in enumerate(measures)
        ]
    if chart_type in ("line", "area"):
        return [ChartSeriesSpec(name=m, column=m, type="line") for m in measures]
    if chart_type == "scatter":
        return [ChartSeriesSpec(name=measures[0], column=measures[0], type="scatter")]
    return [ChartSeriesSpec(name=m, column=m, type=chart_type if chart_type != "column" else "bar") for m in measures]


def build_chart_spec(
    *,
    columns: list[str] | None,
    rows: list[list] | None,
    visualization_intent: dict[str, Any] | None,
    question: str = "",
    assembly_mode: str | None = None,
) -> ChartSpec:
    """根据表格数据与 visualization 意图生成 ChartSpec。"""
    intent = normalize_visualization_intent(visualization_intent or infer_visualization_from_question(question))
    cols = list(columns or [])
    data = [list(r) for r in (rows or [])]

    if not intent.get("enabled", True):
        return ChartSpec(
            chart_type="none",
            status="skipped",
            reject_reason=intent.get("reason") or "当前问句适合表格展示",
        )

    if not cols or not data:
        return ChartSpec(
            chart_type="none",
            status="rejected",
            reject_reason="无数据，无法生成图表",
        )

    if len(data) > _MAX_CHART_ROWS:
        return ChartSpec(
            chart_type="none",
            status="rejected",
            reject_reason=f"结果行数过多（{len(data)} 行），请缩小范围后查看图表",
        )

    measures = [c for i, c in enumerate(cols) if _is_measure_column(c, data, i)]
    if not measures:
        return ChartSpec(
            chart_type="none",
            status="rejected",
            reject_reason="无数值列，无法生成图表",
        )

    if len(data) == 1 and len(measures) == 1 and len(cols) <= 2:
        return ChartSpec(
            chart_type="none",
            status="rejected",
            reject_reason="单值汇总结果不适合图表，建议使用表格查看",
        )

    dim = _pick_dimension(cols, data, measures)
    preferred = intent.get("preferred_types") or ["bar", "line"]
    chart_type = _choose_chart_type(preferred, dim, measures, data, cols, assembly_mode)

    if chart_type == "none" or not _compatible(chart_type, dim, measures, data, cols):
        reason = "当前结果结构不适合生成所选类型图表"
        if intent.get("user_explicit"):
            reason = f"{reason}，以下为表格数据"
        return ChartSpec(
            chart_type="none",
            status="rejected",
            reject_reason=reason,
        )

    options: dict[str, Any] | None = None
    if chart_type == "pie" and dim:
        dim_idx = cols.index(dim)
        if _unique_count(data, dim_idx) > _PIE_MAX_CATEGORIES:
            chart_type = "bar"
            options = {"limit": _TOP_N_BAR, "note": "类别过多，已改用柱状图 Top20"}

    if chart_type in ("bar", "column") and dim:
        dim_idx = cols.index(dim)
        if _unique_count(data, dim_idx) > _BAR_MAX_CATEGORIES:
            options = {"limit": _TOP_N_BAR, "note": f"类别过多，仅展示 Top{_TOP_N_BAR}"}

    y_cols = measures if chart_type != "scatter" else measures[:2]
    if chart_type == "pie":
        y_cols = measures[:1]

    series = _build_series(chart_type, y_cols)
    title = question[:40] + ("…" if len(question) > 40 else "") if question else None

    return ChartSpec(
        chart_type=chart_type,
        title=title,
        x_column=dim if chart_type != "scatter" else y_cols[0] if y_cols else None,
        y_columns=y_cols,
        series=series,
        options=options,
        status="ready",
    )
