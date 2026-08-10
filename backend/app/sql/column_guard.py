"""
SQL 列名校验：对照元数据拦截 LLM 编造的字段名。
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.sql.dialect import parse_sql, render_sql
from app.sql.errors import SqlGuardError
from app.system.sql_context import ResolvedSqlContext
from config.settings import Settings


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


def _collect_output_aliases(parsed: exp.Expression) -> set[str]:
    """SELECT 输出列别名（含中文），供 ORDER BY / GROUP BY 引用校验豁免。"""
    aliases: set[str] = set()
    for node in parsed.find_all(exp.Alias):
        alias = node.alias
        if alias:
            aliases.add(str(alias).lower())
    return aliases


def validate_sql_columns(
    sql: str,
    table_columns: dict[str, set[str]],
    *,
    sql_ctx: ResolvedSqlContext | None = None,
    settings: Settings | None = None,
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
        parsed = parse_sql(sql, sql_ctx=sql_ctx, settings=settings)
    except Exception as exc:
        raise SqlGuardError("PARSE_ERROR", f"SQL 解析失败: {exc}") from exc

    alias_map = _build_alias_map(parsed)
    output_aliases = _collect_output_aliases(parsed)
    queried_tables = set(alias_map.values()) & set(table_columns.keys())
    if not queried_tables:
        return

    errors: list[str] = []
    for col in parsed.find_all(exp.Column):
        col_name = col.name
        if not col_name or col_name == "*":
            continue
        if col_name.lower() in output_aliases:
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


def validate_denied_columns_sql(
    sql: str,
    denied_columns: dict[str, frozenset[str]],
    *,
    sql_ctx: ResolvedSqlContext | None = None,
    settings: Settings | None = None,
) -> None:
    """AST 遍历 SELECT 引用，命中 deny 列则拒绝（DataScope · §11.6）。"""
    if not denied_columns:
        return

    try:
        parsed = parse_sql(sql, sql_ctx=sql_ctx, settings=settings)
    except Exception as exc:
        raise SqlGuardError("PARSE_ERROR", f"SQL 解析失败: {exc}") from exc

    alias_map = _build_alias_map(parsed)
    output_aliases = _collect_output_aliases(parsed)

    for col in parsed.find_all(exp.Column):
        name = col.name
        if not name or name == "*" or name.lower() in output_aliases:
            continue
        ref = col.table
        if ref:
            physical = alias_map.get(str(ref).lower(), str(ref).lower())
            denied = denied_columns.get(physical, frozenset())
            if name in denied:
                raise SqlGuardError(
                    "COLUMN_DENIED",
                    f"禁止查询字段 {physical}.{name}",
                )
        else:
            for physical, denied in denied_columns.items():
                if name in denied and physical in alias_map.values():
                    raise SqlGuardError(
                        "COLUMN_DENIED",
                        f"禁止查询字段 {physical}.{name}",
                    )

