"""
Scope 注入与校验：按 table_scope_binding 动态列名注入 IN 条件（第 13 周）。
"""

from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

from app.policy.effective_policy import EffectivePolicy
from app.sql.dialect import parse_sql, render_sql
from app.sql.errors import SqlGuardError
from app.system.sql_context import ResolvedSqlContext
from config.settings import Settings


def _extract_tables(parsed: exp.Expression) -> set[str]:
    tables: set[str] = set()
    for node in parsed.find_all(exp.Table):
        if node.name:
            tables.add(node.name.lower())
    return tables


def _alias_map(parsed: exp.Expression) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for table in parsed.find_all(exp.Table):
        if not table.name:
            continue
        physical = table.name.lower()
        if table.alias:
            mapping[str(table.alias).lower()] = physical
        mapping[physical] = physical
    return mapping


def _literal_values(node: exp.Expression) -> list[Any]:
    """从 EQ / IN 节点提取字面量值。"""
    values: list[Any] = []
    if isinstance(node, exp.EQ):
        right = node.expression
        if isinstance(right, exp.Literal):
            values.append(right.this)
    elif isinstance(node, exp.In):
        for item in node.expressions or []:
            if isinstance(item, exp.Literal):
                values.append(item.this)
    return values


def _column_matches_binding(
    col: exp.Column,
    alias_map: dict[str, str],
    table: str,
    dim_code: str,
    column_name: str,
) -> bool:
    col_name = (col.name or "").lower()
    if col_name != column_name.lower():
        return False
    ref = col.table
    if ref:
        physical = alias_map.get(str(ref).lower(), str(ref).lower())
        return physical == table
    return True


def _find_scope_literals(
    parsed: exp.Expression,
    alias_map: dict[str, str],
    table: str,
    column_name: str,
) -> list[Any]:
    """在 WHERE 中查找绑定列上的字面量过滤值。"""
    found: list[Any] = []
    for col in parsed.find_all(exp.Column):
        if not _column_matches_binding(col, alias_map, table, "", column_name):
            continue
        parent = col.parent
        if isinstance(parent, exp.EQ):
            found.extend(_literal_values(parent))
        elif isinstance(parent, exp.In) and parent.this == col:
            found.extend(_literal_values(parent))
    return found


def _coerce_values(raw_values: list[Any], grant_values: list[Any]) -> list[Any]:
    """按 grant 值类型做简单类型对齐。"""
    if not grant_values:
        return raw_values
    sample = grant_values[0]
    if isinstance(sample, int):
        out: list[Any] = []
        for v in raw_values:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                out.append(v)
        return out
    return [str(v) for v in raw_values]


def validate_scope_literals(
    sql: str,
    policy: EffectivePolicy,
    *,
    sql_ctx: ResolvedSqlContext | None = None,
    settings: Settings | None = None,
) -> None:
    """
    校验 SQL 中绑定列的字面量均在 grant 内。

    Raises:
        SqlGuardError: SCOPE_VIOLATION
    """
    if policy.is_admin_bypass or not policy.data_grants:
        return

    try:
        parsed = parse_sql(sql, sql_ctx=sql_ctx, settings=settings)
    except Exception as exc:
        raise SqlGuardError("PARSE_ERROR", f"SQL 解析失败: {exc}") from exc

    tables = _extract_tables(parsed)
    alias_map = _alias_map(parsed)

    for table in tables:
        bindings = policy.table_bindings.get(table, [])
        for dim_code, column_name in bindings:
            grant_values = policy.data_grants.get(dim_code)
            if not grant_values:
                continue
            literals = _find_scope_literals(parsed, alias_map, table, column_name)
            if not literals:
                continue
            coerced = _coerce_values(literals, grant_values)
            grant_set = set(_coerce_values(list(grant_values), grant_values))
            for lit in coerced:
                if lit not in grant_set:
                    raise SqlGuardError(
                        "SCOPE_VIOLATION",
                        f"维度 {dim_code} 的值 {lit!r} 不在授权范围 {list(grant_values)[:5]} 内",
                    )


def apply_scope_to_sql(
    sql: str,
    policy: EffectivePolicy,
    *,
    sql_ctx: ResolvedSqlContext | None = None,
    settings: Settings | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    为缺失的 scope 条件注入 AND <column> IN (:scope_<dim>_0, …)。

    Returns:
        (sql, params)
    """
    if policy.is_admin_bypass or not policy.data_grants:
        return sql, {}

    try:
        parsed = parse_sql(sql, sql_ctx=sql_ctx, settings=settings)
    except Exception as exc:
        raise SqlGuardError("PARSE_ERROR", f"SQL 解析失败: {exc}") from exc

    if not isinstance(parsed, exp.Select):
        return sql, {}

    tables = _extract_tables(parsed)
    alias_map = _alias_map(parsed)
    params: dict[str, Any] = {}
    conditions: list[exp.Expression] = []

    for table in tables:
        for dim_code, column_name in policy.table_bindings.get(table, []):
            grant_values = policy.data_grants.get(dim_code)
            if not grant_values:
                continue

            active = policy.active_scopes.get(dim_code)
            effective_values = [active] if active is not None else list(grant_values)

            literals = _find_scope_literals(parsed, alias_map, table, column_name)
            if literals:
                validate_scope_literals(sql, policy, sql_ctx=sql_ctx, settings=settings)
                continue

            table_alias = None
            for node in parsed.find_all(exp.Table):
                if node.name and node.name.lower() == table:
                    table_alias = str(node.alias) if node.alias else table
                    break
            col_ref = f"{table_alias}.{column_name}" if table_alias else column_name

            placeholders: list[str] = []
            for i, val in enumerate(effective_values):
                key = f"scope_{dim_code}_{i}"
                placeholders.append(f":{key}")
                params[key] = val

            in_sql = f"{col_ref} IN ({', '.join(placeholders)})"
            conditions.append(parse_sql(in_sql, sql_ctx=sql_ctx, settings=settings))

    if not conditions:
        return render_sql(parsed, sql_ctx=sql_ctx, settings=settings), params

    where = parsed.args.get("where")
    combined = conditions[0]
    for cond in conditions[1:]:
        combined = exp.and_(combined, cond)
    if where:
        parsed.set("where", exp.and_(where, combined))
    else:
        parsed.set("where", exp.Where(this=combined))

    return render_sql(parsed, sql_ctx=sql_ctx, settings=settings), params
