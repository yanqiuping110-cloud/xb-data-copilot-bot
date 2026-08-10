"""
业务库只读 SQL 执行器。

连接来自 runtime_config 默认数据源；禁止 DML/DDL，仅执行已通过 sql_guard 的 SELECT。
支持 async SQLAlchemy、同步驱动（to_thread）与 ClickHouse HTTP。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import create_engine, text

from app.db.business import (
    get_business_engine,
    get_business_engine_mode,
    get_sync_business_engine,
)
from app.db.sql_policy import BusinessWriteForbiddenError, assert_business_readonly_sql
from app.sql.guard import SqlGuardError
from app.system.connectors import registry
from app.system.runtime_config import resolve_business_dsn
from app.system.sql_context import dsn_to_connect_params


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

    bind_params = params or {}
    dsn = resolve_business_dsn()
    mode = get_business_engine_mode()

    # Excel：执行前确保镜像最新
    if dsn.db_type == "excel":
        conn = registry.get("excel")
        if conn is not None and hasattr(conn, "ensure_mirror"):
            await conn.ensure_mirror(dsn_to_connect_params(dsn))

    if mode == "clickhouse_http" or (
        dsn.db_type == "clickhouse" and mode != "async"
    ):
        return await asyncio.to_thread(
            _execute_clickhouse_http, sql, bind_params, max_rows, dsn
        )

    if mode == "sync":
        engine = get_sync_business_engine()
        if engine is None:
            get_business_engine()
            engine = get_sync_business_engine()
        return await asyncio.to_thread(
            _execute_sync, engine, sql, bind_params, max_rows
        )

    engine = get_business_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(sql), bind_params)
        columns = list(result.keys())
        raw_rows = result.fetchmany(max_rows + 1)
        if len(raw_rows) > max_rows:
            raise SqlGuardError("TOO_MANY_ROWS", f"结果超过 {max_rows} 行上限")
        rows = [[_serialize_cell(cell) for cell in row] for row in raw_rows]
        return columns, rows


def _execute_sync(engine, sql: str, bind_params: dict, max_rows: int):
    with engine.connect() as conn:
        result = conn.execute(text(sql), bind_params)
        columns = list(result.keys())
        raw_rows = result.fetchmany(max_rows + 1)
        if len(raw_rows) > max_rows:
            raise SqlGuardError("TOO_MANY_ROWS", f"结果超过 {max_rows} 行上限")
        return columns, [[_serialize_cell(cell) for cell in row] for row in raw_rows]


def _execute_clickhouse_http(sql: str, bind_params: dict, max_rows: int, dsn) -> tuple[list[str], list[list]]:
    import clickhouse_connect

    # 简单替换命名参数（ClickHouse 客户端参数风格有限；guard 后 params 多为 scope）
    rendered = sql
    for k, v in bind_params.items():
        token = f":{k}"
        if isinstance(v, str):
            rendered = rendered.replace(token, "'" + v.replace("'", "''") + "'")
        elif v is None:
            rendered = rendered.replace(token, "NULL")
        else:
            rendered = rendered.replace(token, str(v))

    http_port = 8123 if int(dsn.port or 0) in (9000, 0) else int(dsn.port)
    client = clickhouse_connect.get_client(
        host=dsn.host,
        port=http_port,
        username=dsn.user or "default",
        password=dsn.password or "",
        database=dsn.database or "default",
    )
    try:
        result = client.query(rendered)
        columns = list(result.column_names)
        raw = result.result_rows[: max_rows + 1]
        if len(raw) > max_rows:
            raise SqlGuardError("TOO_MANY_ROWS", f"结果超过 {max_rows} 行上限")
        rows = [[_serialize_cell(cell) for cell in row] for row in raw]
        return columns, rows
    finally:
        client.close()


def _serialize_cell(value):
    """将 Decimal / datetime 等转为 JSON 友好类型。"""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__") and type(value).__name__ in ("Decimal",):
        return float(value)
    return value
