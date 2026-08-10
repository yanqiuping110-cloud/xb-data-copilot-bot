"""
按当前业务库类型选择 introspect 实现（禁止 Meta 主流程写死 MySQL）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.exceptions import MetaError
from app.system.sql_context import resolve_sql_context
from config.settings import Settings

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


@dataclass(frozen=True)
class IntrospectedColumn:
    column_name: str
    data_type: str
    column_comment_auto: str | None
    is_nullable: bool
    ordinal_position: int


@dataclass(frozen=True)
class IntrospectedTable:
    table_name: str
    table_comment_auto: str | None
    columns: tuple[IntrospectedColumn, ...]


def validate_table_name(table_name: str) -> str:
    name = table_name.strip()
    if not name or not _TABLE_NAME_RE.match(name):
        raise MetaError("INVALID_TABLE_NAME", "表名仅允许字母、数字、下划线", 400)
    return name


class MysqlFamilyIntrospector:
    """MySQL / Doris / StarRocks：information_schema。"""

    def __init__(self, business_session: AsyncSession, database: str):
        self._session = business_session
        self._database = database

    async def introspect_table(self, table_name: str) -> IntrospectedTable:
        name = validate_table_name(table_name)
        table_row = await self._session.execute(
            text(
                """
                SELECT TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :table_name
                """
            ),
            {"db": self._database, "table_name": name},
        )
        table_map = table_row.mappings().first()
        if table_map is None:
            raise MetaError("TABLE_NOT_FOUND", f"业务库中不存在表: {name}", 404)

        col_result = await self._session.execute(
            text(
                """
                SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT, IS_NULLABLE, ORDINAL_POSITION
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
                """
            ),
            {"db": self._database, "table_name": name},
        )
        columns: list[IntrospectedColumn] = []
        for row in col_result.mappings().all():
            columns.append(
                IntrospectedColumn(
                    column_name=str(row["COLUMN_NAME"]),
                    data_type=str(row["COLUMN_TYPE"]),
                    column_comment_auto=row.get("COLUMN_COMMENT") or None,
                    is_nullable=str(row["IS_NULLABLE"]).upper() == "YES",
                    ordinal_position=int(row["ORDINAL_POSITION"]),
                )
            )
        comment = table_map.get("TABLE_COMMENT")
        return IntrospectedTable(
            table_name=name,
            table_comment_auto=comment if comment else None,
            columns=tuple(columns),
        )


# 兼容旧名
BusinessSchemaIntrospector = MysqlFamilyIntrospector


class PostgresqlIntrospector:
    def __init__(self, business_session: AsyncSession, database: str):
        self._session = business_session
        self._database = database

    async def introspect_table(self, table_name: str) -> IntrospectedTable:
        name = validate_table_name(table_name)
        exists = await self._session.execute(
            text(
                """
                SELECT obj_description(c.oid) AS table_comment
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r'
                  AND n.nspname = 'public'
                  AND c.relname = :table_name
                """
            ),
            {"table_name": name},
        )
        table_map = exists.mappings().first()
        if table_map is None:
            raise MetaError("TABLE_NOT_FOUND", f"业务库中不存在表: {name}", 404)

        col_result = await self._session.execute(
            text(
                """
                SELECT
                  a.attname AS column_name,
                  pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                  col_description(a.attrelid, a.attnum) AS column_comment,
                  NOT a.attnotnull AS is_nullable,
                  a.attnum AS ordinal_position
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r'
                  AND n.nspname = 'public'
                  AND c.relname = :table_name
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum
                """
            ),
            {"table_name": name},
        )
        columns = [
            IntrospectedColumn(
                column_name=str(row["column_name"]),
                data_type=str(row["data_type"]),
                column_comment_auto=row.get("column_comment") or None,
                is_nullable=bool(row["is_nullable"]),
                ordinal_position=int(row["ordinal_position"]),
            )
            for row in col_result.mappings().all()
        ]
        return IntrospectedTable(
            table_name=name,
            table_comment_auto=table_map.get("table_comment") or None,
            columns=tuple(columns),
        )


class SqlServerIntrospector:
    def __init__(self, business_session: AsyncSession, database: str):
        self._session = business_session
        self._database = database

    async def introspect_table(self, table_name: str) -> IntrospectedTable:
        name = validate_table_name(table_name)
        table_row = await self._session.execute(
            text(
                """
                SELECT CAST(ep.value AS nvarchar(500)) AS table_comment
                FROM INFORMATION_SCHEMA.TABLES t
                LEFT JOIN sys.tables st ON st.name = t.TABLE_NAME
                LEFT JOIN sys.extended_properties ep
                  ON ep.major_id = st.object_id AND ep.minor_id = 0 AND ep.name = 'MS_Description'
                WHERE t.TABLE_CATALOG = DB_NAME()
                  AND t.TABLE_TYPE = 'BASE TABLE'
                  AND t.TABLE_NAME = :table_name
                """
            ),
            {"table_name": name},
        )
        table_map = table_row.mappings().first()
        if table_map is None:
            raise MetaError("TABLE_NOT_FOUND", f"业务库中不存在表: {name}", 404)

        col_result = await self._session.execute(
            text(
                """
                SELECT
                  c.COLUMN_NAME AS column_name,
                  c.DATA_TYPE AS data_type,
                  CAST(ep.value AS nvarchar(500)) AS column_comment,
                  c.IS_NULLABLE AS is_nullable,
                  c.ORDINAL_POSITION AS ordinal_position
                FROM INFORMATION_SCHEMA.COLUMNS c
                LEFT JOIN sys.columns sc
                  ON sc.name = c.COLUMN_NAME
                 AND sc.object_id = OBJECT_ID(QUOTENAME(c.TABLE_SCHEMA) + '.' + QUOTENAME(c.TABLE_NAME))
                LEFT JOIN sys.extended_properties ep
                  ON ep.major_id = sc.object_id AND ep.minor_id = sc.column_id AND ep.name = 'MS_Description'
                WHERE c.TABLE_NAME = :table_name
                ORDER BY c.ORDINAL_POSITION
                """
            ),
            {"table_name": name},
        )
        columns = [
            IntrospectedColumn(
                column_name=str(row["column_name"]),
                data_type=str(row["data_type"]),
                column_comment_auto=row.get("column_comment") or None,
                is_nullable=str(row["is_nullable"]).upper() == "YES",
                ordinal_position=int(row["ordinal_position"]),
            )
            for row in col_result.mappings().all()
        ]
        return IntrospectedTable(
            table_name=name,
            table_comment_auto=table_map.get("table_comment") or None,
            columns=tuple(columns),
        )


class ClickhouseIntrospector:
    def __init__(self, business_session: AsyncSession, database: str):
        self._session = business_session
        self._database = database

    async def introspect_table(self, table_name: str) -> IntrospectedTable:
        name = validate_table_name(table_name)
        col_result = await self._session.execute(
            text(
                """
                SELECT
                  name AS column_name,
                  type AS data_type,
                  comment AS column_comment,
                  position AS ordinal_position
                FROM system.columns
                WHERE database = :db AND table = :table_name
                ORDER BY position
                """
            ),
            {"db": self._database, "table_name": name},
        )
        rows = list(col_result.mappings().all())
        if not rows:
            raise MetaError("TABLE_NOT_FOUND", f"业务库中不存在表: {name}", 404)
        columns = [
            IntrospectedColumn(
                column_name=str(row["column_name"]),
                data_type=str(row["data_type"]),
                column_comment_auto=row.get("column_comment") or None,
                is_nullable="Nullable" in str(row["data_type"]),
                ordinal_position=int(row["ordinal_position"]),
            )
            for row in rows
        ]
        return IntrospectedTable(
            table_name=name,
            table_comment_auto=None,
            columns=tuple(columns),
        )


class OracleIntrospector:
    def __init__(self, business_session: AsyncSession, database: str):
        self._session = business_session
        self._database = database

    async def introspect_table(self, table_name: str) -> IntrospectedTable:
        name = validate_table_name(table_name)
        table_row = await self._session.execute(
            text(
                """
                SELECT comments AS table_comment
                FROM all_tab_comments
                WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA')
                  AND table_name = UPPER(:table_name)
                """
            ),
            {"table_name": name},
        )
        table_map = table_row.mappings().first()
        col_result = await self._session.execute(
            text(
                """
                SELECT
                  c.column_name AS column_name,
                  c.data_type AS data_type,
                  cc.comments AS column_comment,
                  CASE WHEN c.nullable = 'Y' THEN 1 ELSE 0 END AS is_nullable,
                  c.column_id AS ordinal_position
                FROM all_tab_columns c
                LEFT JOIN all_col_comments cc
                  ON cc.owner = c.owner AND cc.table_name = c.table_name
                 AND cc.column_name = c.column_name
                WHERE c.owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA')
                  AND c.table_name = UPPER(:table_name)
                ORDER BY c.column_id
                """
            ),
            {"table_name": name},
        )
        rows = list(col_result.mappings().all())
        if not rows:
            raise MetaError("TABLE_NOT_FOUND", f"业务库中不存在表: {name}", 404)
        columns = [
            IntrospectedColumn(
                column_name=str(row["column_name"]),
                data_type=str(row["data_type"]),
                column_comment_auto=row.get("column_comment") or None,
                is_nullable=bool(row["is_nullable"]),
                ordinal_position=int(row["ordinal_position"]),
            )
            for row in rows
        ]
        return IntrospectedTable(
            table_name=name,
            table_comment_auto=(table_map or {}).get("table_comment") or None,
            columns=tuple(columns),
        )


class ExcelSqliteIntrospector:
    def __init__(self, business_session: AsyncSession, database: str):
        self._session = business_session
        self._database = database

    async def introspect_table(self, table_name: str) -> IntrospectedTable:
        name = validate_table_name(table_name)
        exists = await self._session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = :table_name"
            ),
            {"table_name": name},
        )
        if exists.first() is None:
            raise MetaError("TABLE_NOT_FOUND", f"业务库中不存在表: {name}", 404)
        col_result = await self._session.execute(text(f"PRAGMA table_info({name})"))
        columns = []
        for row in col_result.mappings().all():
            columns.append(
                IntrospectedColumn(
                    column_name=str(row["name"]),
                    data_type=str(row["type"] or "TEXT"),
                    column_comment_auto=None,
                    is_nullable=not bool(row["notnull"]),
                    ordinal_position=int(row["cid"]) + 1,
                )
            )
        return IntrospectedTable(
            table_name=name,
            table_comment_auto=None,
            columns=tuple(columns),
        )


def get_introspector(
    business_session: AsyncSession,
    database: str,
    *,
    settings: Settings | None = None,
    db_type: str | None = None,
):
    """按 ResolvedSqlContext / 显式 db_type 选择 introspect 实现。"""
    dtype = (db_type or resolve_sql_context(settings).db_type or "mysql").lower()
    if dtype in ("mysql", "doris", "starrocks"):
        return MysqlFamilyIntrospector(business_session, database)
    if dtype == "postgresql":
        return PostgresqlIntrospector(business_session, database)
    if dtype == "sqlserver":
        return SqlServerIntrospector(business_session, database)
    if dtype == "clickhouse":
        return ClickhouseIntrospector(business_session, database)
    if dtype == "oracle":
        return OracleIntrospector(business_session, database)
    if dtype == "excel":
        return ExcelSqliteIntrospector(business_session, database)
    raise MetaError("UNSUPPORTED_DB_TYPE", f"暂不支持 introspect：{dtype}", 400)
