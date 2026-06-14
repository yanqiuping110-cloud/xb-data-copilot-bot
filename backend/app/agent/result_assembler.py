"""
分步 SQL 中间结果组装：按 plan 做 join / pivot / 列对齐。
"""

from __future__ import annotations

from typing import Any

from app.agent.plan_compare import short_entity_label

_JOIN_KEY_PRIORITY = (
    "年级",
    "grade",
    "班级",
    "class",
    "sch_id",
    "学校",
    "日期",
    "date",
    "dt",
    "月份",
    "month",
    "周",
    "week",
    "项目",
    "project",
)


def _row_dicts(columns: list[str], rows: list[list]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({columns[i]: row[i] for i in range(min(len(columns), len(row)))})
    return out


def _find_join_key(columns_a: list[str], columns_b: list[str]) -> str | None:
    set_b = set(columns_b)
    for hint in _JOIN_KEY_PRIORITY:
        for col in columns_a:
            if col in set_b and (col == hint or hint in col.lower() or hint in col):
                return col
    for col in columns_a:
        if col in set_b:
            return col
    return None


def _is_numeric(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value))
        return True
    except (TypeError, ValueError):
        return False


def join_result_sets(
    left_columns: list[str],
    left_rows: list[list],
    right_columns: list[str],
    right_rows: list[list],
) -> tuple[list[str], list[list]]:
    """按公共键内连接两个结果集；无公共键时横向拼接（列对齐）。"""
    if not left_rows and right_rows:
        return list(right_columns), [list(r) for r in right_rows]
    if not right_rows:
        return list(left_columns), [list(r) for r in left_rows]

    key = _find_join_key(left_columns, right_columns)
    if not key:
        return _concat_columns(left_columns, left_rows, right_columns, right_rows)

    left_idx = left_columns.index(key)
    right_idx = right_columns.index(key)
    right_map: dict[Any, list] = {}
    for row in right_rows:
        if right_idx < len(row):
            right_map[row[right_idx]] = row

    out_columns = list(left_columns)
    for col in right_columns:
        if col != key and col not in out_columns:
            out_columns.append(col)

    out_rows: list[list] = []
    for left_row in left_rows:
        if left_idx >= len(left_row):
            continue
        match = right_map.get(left_row[left_idx])
        if match is None:
            continue
        merged: dict[str, Any] = {}
        for i, col in enumerate(left_columns):
            if i < len(left_row):
                merged[col] = left_row[i]
        for i, col in enumerate(right_columns):
            if col == key:
                continue
            if i < len(match):
                merged[col] = match[i]
        out_rows.append([merged.get(c) for c in out_columns])
    return out_columns, out_rows


def _concat_columns(
    left_columns: list[str],
    left_rows: list[list],
    right_columns: list[str],
    right_rows: list[list],
) -> tuple[list[str], list[list]]:
    """无公共键时按行序横向拼接（行数取较大值）。"""
    out_columns = list(left_columns)
    for col in right_columns:
        if col not in out_columns:
            out_columns.append(f"{col}_右")
        else:
            out_columns.append(f"{col}_2")

    max_len = max(len(left_rows), len(right_rows))
    out_rows: list[list] = []
    for i in range(max_len):
        row: list[Any] = []
        if i < len(left_rows):
            row.extend(left_rows[i])
        else:
            row.extend([None] * len(left_columns))
        if i < len(right_rows):
            right_row = right_rows[i]
            for j, col in enumerate(right_columns):
                suffix = "" if col not in left_columns else "_2"
                row.append(right_row[j] if j < len(right_row) else None)
        else:
            row.extend([None] * len(right_columns))
        out_rows.append(row)
    return out_columns, out_rows


def pivot_wide(
    columns: list[str],
    rows: list[list],
    pivot_hint: str,
) -> tuple[list[str], list[list]]:
    """
    将长表按 pivot 列透视成宽表。

    pivot_hint 匹配列名（子串或相等）；其余数值列作为 value。
    """
    if not columns or not rows:
        return columns, rows

    pivot_col = None
    hint_lower = pivot_hint.lower()
    for col in columns:
        if col == pivot_hint or hint_lower in col.lower() or pivot_hint in col:
            pivot_col = col
            break
    if pivot_col is None:
        return columns, rows

    pivot_idx = columns.index(pivot_col)
    value_cols = [
        c
        for i, c in enumerate(columns)
        if i != pivot_idx and any(_is_numeric(r[i]) for r in rows if i < len(r))
    ]
    if not value_cols:
        value_cols = [c for i, c in enumerate(columns) if i != pivot_idx]

    dim_cols = [c for c in columns if c not in value_cols and c != pivot_col]
    pivot_values: list[Any] = []
    for row in rows:
        if pivot_idx < len(row) and row[pivot_idx] not in pivot_values:
            pivot_values.append(row[pivot_idx])

    out_columns = list(dim_cols)
    for pv in pivot_values:
        label = str(pv) if pv is not None else "空"
        for vc in value_cols:
            out_columns.append(f"{label}_{vc}")

    grouped: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key_parts = tuple(row[columns.index(c)] if c in columns and columns.index(c) < len(row) else None for c in dim_cols)
        bucket = grouped.setdefault(key_parts, {c: key_parts[i] for i, c in enumerate(dim_cols)})
        pv = row[pivot_idx] if pivot_idx < len(row) else None
        pv_label = str(pv) if pv is not None else "空"
        for vc in value_cols:
            vi = columns.index(vc)
            if vi < len(row):
                bucket[f"{pv_label}_{vc}"] = row[vi]

    out_rows = [[bucket.get(c) for c in out_columns] for bucket in grouped.values()]
    return out_columns, out_rows


def _find_date_join_column(columns: list[str], join_key: str | None = None) -> str | None:
    """在列名中找日期维（用于多活动按日对齐）。"""
    if join_key:
        for col in columns:
            if col == join_key or join_key in col:
                return col
    for hint in _DATE_JOIN_KEYS:
        for col in columns:
            if col == hint or hint in col.lower() or hint in col:
                return col
    return _find_join_key(columns, columns)


def _prefix_value_columns(
    columns: list[str],
    rows: list[list],
    entity_label: str,
    join_col: str,
) -> tuple[list[str], list[list]]:
    """非日期列加实体前缀，避免 join 后列名冲突。"""
    new_cols: list[str] = []
    for col in columns:
        if col == join_col:
            new_cols.append(join_col)
        else:
            prefix = f"{entity_label}_{col}"
            new_cols.append(prefix if prefix not in new_cols else col)
    return new_cols, [list(r) for r in rows]


def assemble_compare_by_date(
    intermediate_results: list[dict[str, Any]],
    *,
    join_key: str | None = None,
) -> tuple[list[str], list[list]]:
    """
    多活动分步 SQL 结果按日期外连接合并（宽表对比）。

    每步结果先给指标列加 entity_label 前缀，再按日期列对齐。
    """
    if not intermediate_results:
        return [], []

    join_key = join_key or "日期"
    prefixed: list[tuple[list[str], list[list], str]] = []

    for ir in intermediate_results:
        cols = list(ir.get("columns") or [])
        rows = [list(r) for r in ir.get("rows") or []]
        if not cols or not rows:
            continue
        label = str(ir.get("entity_label") or ir.get("goal") or f"步骤{ir.get('step_id')}")
        label = short_entity_label(label, max_len=20)
        date_col = _find_date_join_column(cols, join_key)
        if not date_col:
            date_col = cols[0]
        p_cols, p_rows = _prefix_value_columns(cols, rows, label, date_col)
        prefixed.append((p_cols, p_rows, date_col))

    if not prefixed:
        return [], []
    if len(prefixed) == 1:
        return prefixed[0][0], prefixed[0][1]

    merged_cols, merged_rows = prefixed[0][0], prefixed[0][1]
    join_col = prefixed[0][2]
    for p_cols, p_rows, date_col in prefixed[1:]:
        key = join_col if join_col in p_cols else date_col
        merged_cols, merged_rows = join_result_sets(merged_cols, merged_rows, p_cols, p_rows)
        if key in p_cols:
            join_col = key

    return merged_cols, merged_rows


def assemble_intermediate_results(
    intermediate_results: list[dict[str, Any]],
    plan: dict[str, Any] | None,
) -> tuple[list[str], list[list], str]:
    """
    将分步 SQL 中间结果组装为最终表格。

    Returns:
        (columns, rows, assembly_mode) — mode: single | pivot | join | empty
    """
    if not intermediate_results:
        return [], [], "empty"

    assembly_mode = (plan or {}).get("assembly_mode")
    join_key = (plan or {}).get("join_key")

    if assembly_mode == "join_by_date" or (plan or {}).get("multi_sql"):
        cols, rows = assemble_compare_by_date(
            intermediate_results,
            join_key=join_key,
        )
        if cols and rows:
            return cols, rows, "join_by_date"

    if len(intermediate_results) == 1:
        ir = intermediate_results[0]
        return list(ir.get("columns") or []), [list(r) for r in ir.get("rows") or []], "single"

    pivot_hint = None
    for ir in reversed(intermediate_results):
        if ir.get("pivot_hint"):
            pivot_hint = str(ir["pivot_hint"])
            break
    if not pivot_hint and plan:
        for step in reversed(plan.get("steps") or []):
            if step.get("pivot_hint"):
                pivot_hint = str(step["pivot_hint"])
                break

    if pivot_hint:
        last = intermediate_results[-1]
        cols, rows = pivot_wide(
            list(last.get("columns") or []),
            [list(r) for r in last.get("rows") or []],
            pivot_hint,
        )
        if cols and rows:
            return cols, rows, "pivot"

    merged_cols = list(intermediate_results[0].get("columns") or [])
    merged_rows = [list(r) for r in intermediate_results[0].get("rows") or []]
    for ir in intermediate_results[1:]:
        merged_cols, merged_rows = join_result_sets(
            merged_cols,
            merged_rows,
            list(ir.get("columns") or []),
            [list(r) for r in ir.get("rows") or []],
        )
    return merged_cols, merged_rows, "join"


def format_prior_results_summary(prior_results: list[dict[str, Any]]) -> str:
    """压缩前几步 SQL 结果，供下一步 LLM 参考。"""
    if not prior_results:
        return "（尚无已完成步骤结果）"
    lines = ["【已完成步骤结果摘要】"]
    for ir in prior_results:
        step_id = ir.get("step_id")
        goal = ir.get("goal") or ""
        cols = ir.get("columns") or []
        row_count = ir.get("row_count") or len(ir.get("rows") or [])
        sample = (ir.get("rows") or [])[:2]
        lines.append(
            f"- 步骤 {step_id} {goal}: 列={cols[:8]} 行数={row_count} 样例={sample}"
        )
    return "\n".join(lines)


def combine_step_sqls(intermediate_results: list[dict[str, Any]]) -> str:
    """合并各步 SQL 为审计展示文本。"""
    parts: list[str] = []
    for ir in intermediate_results:
        step_id = ir.get("step_id")
        goal = ir.get("goal") or ""
        sql = ir.get("sql") or ""
        parts.append(f"-- 步骤 {step_id}: {goal}\n{sql}")
    return "\n\n".join(parts).strip()
