"""
SQL 列名校验：对照元数据拦截 LLM 编造的字段名。
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.sql.guard import SqlGuardError


def _build_alias_map(parsed: exp.Expression) -> dict[str, str]:
    """别名（小写）→ 物理表名（小写）。"""
    alias_map: dict[str, str] = {}
    for table in parsed.find_all(exp.Table):
        name = table.name
        if not name:
            continue
        physical = name.lower()
        alias = table.alias
        if alias:
            alias_map[str(alias).lower()] = physical
        alias_map[physical] = physical
    return alias_map


def validate_sql_columns(
    sql: str,
    table_columns: dict[str, set[str]],
) -> None:
    """
    校验 SQL 中引用的列是否存在于元数据。

    Args:
        sql: 已通过 validate_sql 的 SELECT 语句。
        table_columns: 物理表名（小写）→ 可用列名集合。

    Raises:
        SqlGuardError: 列名不存在于元数据（code=COLUMN_NOT_FOUND）。
    """
    if not table_columns:
        return

    try:
        parsed = sqlglot.parse_one(sql.strip().rstrip(";"), read="mysql")
    except Exception as exc:
        raise SqlGuardError("PARSE_ERROR", f"SQL 解析失败: {exc}") from exc

    alias_map = _build_alias_map(parsed)
    queried_tables = set(alias_map.values()) & set(table_columns.keys())
    if not queried_tables:
        return

    errors: list[str] = []
    for col in parsed.find_all(exp.Column):
        col_name = col.name
        if not col_name or col_name == "*":
            continue

        table_ref = col.table
        if table_ref:
            tkey = str(table_ref).lower()
            physical = alias_map.get(tkey, tkey if tkey in table_columns else None)
            if physical and physical in table_columns:
                if col_name not in table_columns[physical]:
                    available = ", ".join(sorted(table_columns[physical])[:12])
                    errors.append(
                        f"{physical}.{col_name} 不存在（可用列：{available}）"
                    )
        elif queried_tables:
            if not any(col_name in table_columns[t] for t in queried_tables):
                errors.append(f"字段 {col_name} 在查询表中不存在")

    if errors:
        raise SqlGuardError("COLUMN_NOT_FOUND", "；".join(errors[:3]))

