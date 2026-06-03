"""
从业务库 information_schema 只读拉取表/字段结构（introspect）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.exceptions import MetaError

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


@dataclass(frozen=True)
class IntrospectedColumn:
    """业务库字段快照。"""

    column_name: str
    data_type: str
    column_comment_auto: str | None
    is_nullable: bool
    ordinal_position: int


@dataclass(frozen=True)
class IntrospectedTable:
    """业务库表结构快照（不落 copilot 库）。"""

    table_name: str
    table_comment_auto: str | None
    columns: tuple[IntrospectedColumn, ...]


def validate_table_name(table_name: str) -> str:
    """校验表名，防注入。"""
    name = table_name.strip()
    if not name or not _TABLE_NAME_RE.match(name):
        raise MetaError("INVALID_TABLE_NAME", "表名仅允许字母、数字、下划线", 400)
    return name


class BusinessSchemaIntrospector:
    """只读访问业务库 information_schema。"""

    def __init__(self, business_session: AsyncSession, database: str):
        self._session = business_session
        self._database = database

    async def introspect_table(self, table_name: str) -> IntrospectedTable:
        """拉取单表 COMMENT 与全部字段类型/备注。"""
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
