"""
SQL 安全网关：仅 SELECT、表白名单、强制 LIMIT、学校账户须含 sch_id。

MVP 阶段与 LangGraph validate_sql / apply_policy 节点职责一致，后续 LangGraph 复用本模块。
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.core.context import UserContext
from app.db.sql_policy import BusinessWriteForbiddenError, assert_business_readonly_sql
from app.policy.role_policy import applies_sch_id_filter
from app.sql.whitelist import SCH_ID_COLUMN, get_allowed_tables
from config.settings import Settings, get_settings


class SqlGuardError(Exception):
    """SQL 校验或策略拒绝。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _policy_to_guard(exc: BusinessWriteForbiddenError) -> SqlGuardError:
    return SqlGuardError(exc.code, exc.message)


def _extract_tables(parsed: exp.Expression) -> set[str]:
    """从 AST 提取物理表名（小写）。"""
    tables: set[str] = set()
    for node in parsed.find_all(exp.Table):
        name = node.name
        if name:
            tables.add(name.lower())
    return tables


def validate_sql(
    sql: str,
    ctx: UserContext,
    *,
    max_rows: int,
    settings: Settings | None = None,
) -> str:
    """
    校验 SQL 并返回带 LIMIT 的最终语句（MySQL 方言）。

    Raises:
        SqlGuardError: 非 SELECT、多语句、表不在白名单、学校账户缺 sch_id 等。
    """
    try:
        assert_business_readonly_sql(sql)
    except BusinessWriteForbiddenError as exc:
        raise _policy_to_guard(exc) from exc

    stripped = sql.strip().rstrip(";")

    try:
        parsed = sqlglot.parse_one(stripped, read="mysql")
    except Exception as exc:
        raise SqlGuardError("PARSE_ERROR", f"SQL 解析失败: {exc}") from exc

    if not isinstance(parsed, exp.Select):
        raise SqlGuardError("NOT_SELECT", "仅允许 SELECT 查询")

    tables = _extract_tables(parsed)
    if not tables:
        raise SqlGuardError("NO_TABLE", "未识别到查询表")
    unknown = tables - get_allowed_tables()
    if unknown:
        raise SqlGuardError(
            "TABLE_NOT_ALLOWED",
            f"表不在白名单: {', '.join(sorted(unknown))}",
        )

    s = settings or get_settings()
    if applies_sch_id_filter(ctx, settings=s):
        if SCH_ID_COLUMN not in stripped.lower():
            raise SqlGuardError(
                "MISSING_SCH_ID",
                f"学校账户查询必须包含 {SCH_ID_COLUMN} 条件",
            )

    if parsed.args.get("limit") is None:
        parsed = parsed.limit(max_rows)
    else:
        limit_node = parsed.args["limit"]
        if isinstance(limit_node, exp.Limit):
            try:
                val = int(limit_node.expression.this)
                if val > max_rows:
                    parsed = parsed.limit(max_rows)
            except (TypeError, ValueError, AttributeError):
                parsed = parsed.limit(max_rows)

    return parsed.sql(dialect="mysql")


def validate_probe_sql(
    sql: str,
    ctx: UserContext,
    *,
    max_rows: int = 10,
    settings: Settings | None = None,
) -> str:
    """
    探查 SQL 校验：仅 SELECT、表白名单、强制 LIMIT≤max_rows（默认 10）。

    供 run_probe_sql 工具使用。
    """
    capped = min(max_rows, 10)
    return validate_sql(sql, ctx, max_rows=capped, settings=settings)
