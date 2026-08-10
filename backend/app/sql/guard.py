"""
SQL 安全网关：仅 SELECT、表白名单、强制 LIMIT、学校账户须含 sch_id。

MVP 阶段与 LangGraph validate_sql / apply_policy 节点职责一致，后续 LangGraph 复用本模块。
"""

from __future__ import annotations

from sqlglot import exp

from app.core.context import UserContext
from app.db.sql_policy import BusinessWriteForbiddenError, assert_business_readonly_sql
from app.policy.effective_policy import EffectivePolicy
from app.policy.role_policy import applies_sch_id_filter
from app.sql.column_guard import validate_denied_columns_sql
from app.sql.dialect import parse_sql, render_sql
from app.sql.errors import SqlGuardError
from app.sql.whitelist import SCH_ID_COLUMN, get_allowed_tables
from app.system.sql_context import ResolvedSqlContext
from config.settings import Settings, get_settings


def _policy_to_guard(exc: BusinessWriteForbiddenError) -> SqlGuardError:
    return SqlGuardError(exc.code, exc.message)


def _cte_alias_names(parsed: exp.Expression) -> set[str]:
    """CTE 别名不应计入物理表白名单。"""
    names: set[str] = set()
    for cte in parsed.find_all(exp.CTE):
        alias = cte.alias_or_name
        if alias:
            names.add(str(alias).lower())
    return names


def _extract_tables(parsed: exp.Expression) -> set[str]:
    """从 AST 提取物理表名（小写），排除 CTE 别名。"""
    cte_names = _cte_alias_names(parsed)
    tables: set[str] = set()
    for node in parsed.find_all(exp.Table):
        name = node.name
        if name and name.lower() not in cte_names:
            tables.add(name.lower())
    return tables


def _outer_select(parsed: exp.Expression) -> exp.Select | None:
    """取最外层 SELECT（含 WITH ... SELECT）。"""
    if isinstance(parsed, exp.Select):
        return parsed
    if isinstance(parsed, exp.With) and isinstance(parsed.this, exp.Select):
        return parsed.this
    return None


def _is_readonly_query(parsed: exp.Expression) -> bool:
    return _outer_select(parsed) is not None


def validate_sql(
    sql: str,
    ctx: UserContext,
    *,
    max_rows: int,
    settings: Settings | None = None,
    policy: EffectivePolicy | None = None,
    sql_ctx: ResolvedSqlContext | None = None,
) -> str:
    """
    校验 SQL 并返回带 LIMIT 的最终语句（方言来自 ResolvedSqlContext）。

    Raises:
        SqlGuardError: 非 SELECT、多语句、表不在白名单、学校账户缺 sch_id 等。
    """
    try:
        assert_business_readonly_sql(sql)
    except BusinessWriteForbiddenError as exc:
        raise _policy_to_guard(exc) from exc

    stripped = sql.strip().rstrip(";")

    try:
        parsed = parse_sql(stripped, sql_ctx=sql_ctx, settings=settings)
    except Exception as exc:
        raise SqlGuardError("PARSE_ERROR", f"SQL 解析失败: {exc}") from exc

    if not _is_readonly_query(parsed):
        raise SqlGuardError("NOT_SELECT", "仅允许 SELECT 查询")

    outer = _outer_select(parsed)
    assert outer is not None

    tables = _extract_tables(parsed)
    if not tables:
        raise SqlGuardError("NO_TABLE", "未识别到查询表")

    allowed = (
        policy.allowed_tables
        if policy is not None and not policy.is_admin_bypass
        else get_allowed_tables()
    )
    if policy is not None and policy.is_admin_bypass:
        allowed = policy.allowed_tables or get_allowed_tables()

    unknown = tables - allowed
    if unknown:
        raise SqlGuardError(
            "TABLE_NOT_ALLOWED",
            f"表不在白名单: {', '.join(sorted(unknown))}",
        )

    if policy is not None and policy.denied_columns:
        validate_denied_columns_sql(
            stripped, policy.denied_columns, sql_ctx=sql_ctx, settings=settings
        )

    s = settings or get_settings()
    if applies_sch_id_filter(ctx, settings=s):
        if SCH_ID_COLUMN not in stripped.lower():
            raise SqlGuardError(
                "MISSING_SCH_ID",
                f"学校账户查询必须包含 {SCH_ID_COLUMN} 条件",
            )

    if outer.args.get("limit") is None:
        limited = outer.limit(max_rows)
        if isinstance(parsed, exp.With):
            parsed.set("this", limited)
        else:
            parsed = limited
    else:
        limit_node = outer.args["limit"]
        if isinstance(limit_node, exp.Limit):
            try:
                val = int(limit_node.expression.this)
                if val > max_rows:
                    limited = outer.limit(max_rows)
                    if isinstance(parsed, exp.With):
                        parsed.set("this", limited)
                    else:
                        parsed = limited
            except (TypeError, ValueError, AttributeError):
                limited = outer.limit(max_rows)
                if isinstance(parsed, exp.With):
                    parsed.set("this", limited)
                else:
                    parsed = limited

    return render_sql(parsed, sql_ctx=sql_ctx, settings=settings)


def validate_probe_sql(
    sql: str,
    ctx: UserContext,
    *,
    max_rows: int = 10,
    settings: Settings | None = None,
    policy: EffectivePolicy | None = None,
    sql_ctx: ResolvedSqlContext | None = None,
) -> str:
    """
    探查 SQL 校验：仅 SELECT、表白名单、强制 LIMIT≤max_rows（默认 10）。

    供 run_probe_sql 工具使用。
    """
    capped = min(max_rows, 10)
    return validate_sql(
        sql,
        ctx,
        max_rows=capped,
        settings=settings,
        policy=policy,
        sql_ctx=sql_ctx,
    )
