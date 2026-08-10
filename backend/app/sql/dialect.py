"""方言感知的 sqlglot 读写助手。"""

from __future__ import annotations

import sqlglot

from app.system.sql_context import ResolvedSqlContext, resolve_sql_context
from config.settings import Settings


def sql_context_or_default(
    sql_ctx: ResolvedSqlContext | None = None,
    *,
    settings: Settings | None = None,
) -> ResolvedSqlContext:
    return sql_ctx or resolve_sql_context(settings)


def parse_sql(
    sql: str,
    *,
    sql_ctx: ResolvedSqlContext | None = None,
    settings: Settings | None = None,
):
    ctx = sql_context_or_default(sql_ctx, settings=settings)
    return sqlglot.parse_one(sql.strip().rstrip(";"), read=ctx.sqlglot_read)


def render_sql(
    parsed,
    *,
    sql_ctx: ResolvedSqlContext | None = None,
    settings: Settings | None = None,
) -> str:
    ctx = sql_context_or_default(sql_ctx, settings=settings)
    return parsed.sql(dialect=ctx.sqlglot_dialect)
