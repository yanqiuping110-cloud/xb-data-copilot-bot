"""
探查 SQL 工具：业务只读库 LIMIT≤10 快速验证（§11.7.2 · 第 8 周）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.sql.executor import execute_readonly
from app.sql.guard import SqlGuardError, validate_probe_sql
from config.settings import Settings

_PROBE_MAX_ROWS = 10


async def run_probe_sql(
    session: AsyncSession,
    settings: Settings,
    *,
    ctx: UserContext,
    sql: str,
) -> dict[str, Any]:
    """
    执行探查 SQL：仅 SELECT，强制 LIMIT≤10，超时 AGENT_PROBE_TIMEOUT_SEC。

    数据源：业务只读库（经 sql_guard）。
    """
    _ = session
    if not (sql or "").strip():
        return {"error": "EMPTY_SQL", "tool": "run_probe_sql"}

    try:
        safe_sql = validate_probe_sql(
            sql,
            ctx,
            max_rows=_PROBE_MAX_ROWS,
            settings=settings,
            policy=getattr(ctx, "effective_policy", None),
        )
    except SqlGuardError as exc:
        return {"error": exc.code, "message": exc.message, "tool": "run_probe_sql"}

    try:
        columns, rows = await asyncio.wait_for(
            execute_readonly(safe_sql, max_rows=_PROBE_MAX_ROWS),
            timeout=settings.agent_probe_timeout_sec,
        )
    except asyncio.TimeoutError:
        return {
            "error": "PROBE_TIMEOUT",
            "message": f"探查超时（>{settings.agent_probe_timeout_sec}s）",
            "tool": "run_probe_sql",
        }
    except SqlGuardError as exc:
        return {"error": exc.code, "message": exc.message, "tool": "run_probe_sql"}
    except Exception as exc:
        return {"error": "PROBE_EXEC_ERROR", "message": str(exc)[:300], "tool": "run_probe_sql"}

    return {
        "sql": safe_sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "count": len(rows),
    }
