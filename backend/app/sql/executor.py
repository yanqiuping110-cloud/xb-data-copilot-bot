"""
业务库只读 SQL 执行器。

连接 MYSQL_BUSINESS_*：禁止 DML/DDL，仅执行已通过 sql_guard 的 SELECT。
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.business import get_business_engine
from app.db.sql_policy import BusinessWriteForbiddenError, assert_business_readonly_sql
from app.sql.guard import SqlGuardError


async def execute_readonly(
    sql: str,
    params: dict | None = None,
    *,
    max_rows: int,
) -> tuple[list[str], list[list]]:
    """
    执行业务只读查询。

    Returns:
        (columns, rows) — rows 为二维列表，单元格转为 JSON 可序列化类型。
    """
    try:
        assert_business_readonly_sql(sql)
    except BusinessWriteForbiddenError as exc:
        raise SqlGuardError(exc.code, exc.message) from exc

    engine = get_business_engine()
    bind_params = params or {}
    async with engine.connect() as conn:
        result = await conn.execute(text(sql), bind_params)
        columns = list(result.keys())
        raw_rows = result.fetchmany(max_rows + 1)
        if len(raw_rows) > max_rows:
            raise SqlGuardError("TOO_MANY_ROWS", f"结果超过 {max_rows} 行上限")
        rows = [[_serialize_cell(cell) for cell in row] for row in raw_rows]
        return columns, rows


def _serialize_cell(value):
    """将 Decimal / datetime 等转为 JSON 友好类型。"""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__") and type(value).__name__ in ("Decimal",):
        return float(value)
    return value
