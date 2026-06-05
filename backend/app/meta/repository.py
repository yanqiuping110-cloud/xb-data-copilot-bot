"""
copilot 库元数据表读写。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.effective import effective_description
from app.meta.introspector import IntrospectedColumn, IntrospectedTable


@dataclass
class TableMetaRow:
    """copilot_table_meta 一行。"""

    id: int
    table_name: str
    table_role: str | None
    biz_domain: str | None
    table_comment_auto: str | None
    description_manual: str | None
    grain: str | None
    sch_id_column: str
    last_introspected_at: datetime | None
    status: int


@dataclass
class IndexableColumnRow:
    """ES 字段索引一行。"""

    column_id: int
    table_id: int
    table_name: str
    column_name: str
    description_manual: str | None
    column_comment_auto: str | None
    alias_json: str | None
    column_role: str | None


@dataclass
class IndexableMetricRow:
    """ES 指标索引一行。"""

    metric_id: int
    metric_code: str
    metric_name: str
    description: str | None
    formula_text: str | None
    relevant_tables: str | None
    alias_json: str | None


@dataclass
class IndexableFieldValueRow:
    """ES 字段取值索引一行。"""

    field_value_id: int
    column_id: int
    table_name: str
    column_name: str
    value_text: str
    display_label: str | None
    alias_json: str | None


@dataclass
class ColumnMetaRow:
    """copilot_column_meta 一行。"""

    id: int
    table_id: int
    column_name: str
    ordinal_position: int
    data_type: str | None
    column_comment_auto: str | None
    description_manual: str | None
    column_role: str | None
    alias_json: str | None
    is_nullable: int
    status: int

    @property
    def effective_description(self) -> str | None:
        return effective_description(self.description_manual, self.column_comment_auto)


class MetaRepository:
    """元数据 CRUD（copilot 库）。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_table_by_name(self, table_name: str) -> TableMetaRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, table_name, table_role, biz_domain, table_comment_auto,
                       description_manual, grain, sch_id_column, last_introspected_at, status
                FROM copilot_table_meta
                WHERE table_name = :name AND deleted = 0
                """
            ),
            {"name": table_name},
        )
        row = result.mappings().first()
        return _map_table(row) if row else None

    async def get_table(self, table_id: int) -> TableMetaRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, table_name, table_role, biz_domain, table_comment_auto,
                       description_manual, grain, sch_id_column, last_introspected_at, status
                FROM copilot_table_meta
                WHERE id = :id AND deleted = 0
                """
            ),
            {"id": table_id},
        )
        row = result.mappings().first()
        return _map_table(row) if row else None

    async def list_tables(self, *, offset: int = 0, limit: int = 50) -> list[TableMetaRow]:
        result = await self._session.execute(
            text(
                """
                SELECT id, table_name, table_role, biz_domain, table_comment_auto,
                       description_manual, grain, sch_id_column, last_introspected_at, status
                FROM copilot_table_meta
                WHERE deleted = 0
                ORDER BY table_name
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        return [_map_table(r) for r in result.mappings().all()]

    async def insert_table(
        self,
        *,
        table_name: str,
        table_comment_auto: str | None,
        table_role: str | None = None,
        biz_domain: str | None = None,
        description_manual: str | None = None,
        grain: str | None = None,
        sch_id_column: str = "sch_id",
        last_introspected_at: datetime | None = None,
        status: int = 1,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_table_meta (
                    table_name, table_role, biz_domain, table_comment_auto, description_manual,
                    grain, sch_id_column, last_introspected_at, status, deleted
                ) VALUES (
                    :table_name, :table_role, :biz_domain, :table_comment_auto, :description_manual,
                    :grain, :sch_id_column, :last_introspected_at, :status, 0
                )
                """
            ),
            {
                "table_name": table_name,
                "table_role": table_role,
                "biz_domain": biz_domain,
                "table_comment_auto": table_comment_auto,
                "description_manual": description_manual,
                "grain": grain,
                "sch_id_column": sch_id_column,
                "last_introspected_at": last_introspected_at,
                "status": status,
            },
        )
        return int(result.lastrowid)

    async def update_table_manual_fields(
        self,
        table_id: int,
        *,
        table_role: str | None = None,
        biz_domain: str | None = None,
        description_manual: str | None = None,
        grain: str | None = None,
        sch_id_column: str | None = None,
        status: int | None = None,
    ) -> None:
        table = await self.get_table(table_id)
        if table is None:
            return
        await self._session.execute(
            text(
                """
                UPDATE copilot_table_meta SET
                    table_role = :table_role,
                    biz_domain = :biz_domain,
                    description_manual = :description_manual,
                    grain = :grain,
                    sch_id_column = :sch_id_column,
                    status = :status
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": table_id,
                "table_role": table_role if table_role is not None else table.table_role,
                "biz_domain": biz_domain if biz_domain is not None else table.biz_domain,
                "description_manual": description_manual
                if description_manual is not None
                else table.description_manual,
                "grain": grain if grain is not None else table.grain,
                "sch_id_column": sch_id_column if sch_id_column is not None else table.sch_id_column,
                "status": status if status is not None else table.status,
            },
        )

    async def update_table_auto_fields(
        self,
        table_id: int,
        *,
        table_comment_auto: str | None,
        last_introspected_at: datetime,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_table_meta SET
                    table_comment_auto = :table_comment_auto,
                    last_introspected_at = :last_introspected_at
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": table_id,
                "table_comment_auto": table_comment_auto,
                "last_introspected_at": last_introspected_at,
            },
        )

    async def list_columns(self, table_id: int) -> list[ColumnMetaRow]:
        result = await self._session.execute(
            text(
                """
                SELECT id, table_id, column_name, ordinal_position, data_type,
                       column_comment_auto, description_manual, column_role, alias_json,
                       is_nullable, status
                FROM copilot_column_meta
                WHERE table_id = :table_id AND deleted = 0
                ORDER BY ordinal_position, column_name
                """
            ),
            {"table_id": table_id},
        )
        return [_map_column(r) for r in result.mappings().all()]

    async def get_column_map(self, table_id: int) -> dict[str, ColumnMetaRow]:
        cols = await self.list_columns(table_id)
        return {c.column_name: c for c in cols}

    async def insert_column(
        self,
        *,
        table_id: int,
        column: IntrospectedColumn,
        description_manual: str | None = None,
        column_role: str | None = None,
        alias_json: str | None = None,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_column_meta (
                    table_id, column_name, ordinal_position, data_type, column_comment_auto,
                    description_manual, column_role, alias_json, is_nullable, status, deleted
                ) VALUES (
                    :table_id, :column_name, :ordinal_position, :data_type, :column_comment_auto,
                    :description_manual, :column_role, :alias_json, :is_nullable, 1, 0
                )
                """
            ),
            {
                "table_id": table_id,
                "column_name": column.column_name,
                "ordinal_position": column.ordinal_position,
                "data_type": column.data_type,
                "column_comment_auto": column.column_comment_auto,
                "description_manual": description_manual,
                "column_role": column_role,
                "alias_json": alias_json,
                "is_nullable": 1 if column.is_nullable else 0,
            },
        )
        return int(result.lastrowid)

    async def refresh_column_auto(
        self,
        column_id: int,
        column: IntrospectedColumn,
    ) -> None:
        """仅更新 auto 字段与 status=1（字段重新出现）。"""
        await self._session.execute(
            text(
                """
                UPDATE copilot_column_meta SET
                    ordinal_position = :ordinal_position,
                    data_type = :data_type,
                    column_comment_auto = :column_comment_auto,
                    is_nullable = :is_nullable,
                    status = 1
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": column_id,
                "ordinal_position": column.ordinal_position,
                "data_type": column.data_type,
                "column_comment_auto": column.column_comment_auto,
                "is_nullable": 1 if column.is_nullable else 0,
            },
        )

    async def mark_column_inactive(self, column_id: int) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_column_meta SET status = 0 WHERE id = :id AND deleted = 0
                """
            ),
            {"id": column_id},
        )

    async def get_column(self, column_id: int) -> ColumnMetaRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, table_id, column_name, ordinal_position, data_type,
                       column_comment_auto, description_manual, column_role, alias_json,
                       is_nullable, status
                FROM copilot_column_meta
                WHERE id = :id AND deleted = 0
                """
            ),
            {"id": column_id},
        )
        row = result.mappings().first()
        return _map_column(row) if row else None

    async def update_column_manual(
        self,
        column_id: int,
        *,
        description_manual: str | None = None,
        column_role: str | None = None,
        alias_json: str | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_column_meta SET
                    description_manual = COALESCE(:description_manual, description_manual),
                    column_role = COALESCE(:column_role, column_role),
                    alias_json = COALESCE(:alias_json, alias_json)
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": column_id,
                "description_manual": description_manual,
                "column_role": column_role,
                "alias_json": alias_json,
            },
        )

    async def load_allowed_table_names(self) -> set[str]:
        """问数白名单：status=1 的 table_meta。"""
        result = await self._session.execute(
            text(
                """
                SELECT table_name FROM copilot_table_meta
                WHERE status = 1 AND deleted = 0
                """
            )
        )
        return {str(r["table_name"]).lower() for r in result.mappings().all()}

    async def upsert_field_value(
        self,
        column_id: int,
        *,
        value_text: str,
        display_label: str | None = None,
        alias_json: str | None = None,
    ) -> int:
        """按 column_id + value_text 幂等写入字段取值。"""
        existing = await self._session.execute(
            text(
                """
                SELECT id FROM copilot_field_value
                WHERE column_id = :column_id AND value_text = :value_text AND deleted = 0
                """
            ),
            {"column_id": column_id, "value_text": value_text},
        )
        row = existing.mappings().first()
        if row:
            fid = int(row["id"])
            await self._session.execute(
                text(
                    """
                    UPDATE copilot_field_value SET
                        display_label = :display_label,
                        alias_json = :alias_json,
                        status = 1
                    WHERE id = :id AND deleted = 0
                    """
                ),
                {
                    "id": fid,
                    "display_label": display_label,
                    "alias_json": alias_json,
                },
            )
            return fid

        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_field_value (
                    column_id, value_text, display_label, alias_json, status, deleted
                ) VALUES (
                    :column_id, :value_text, :display_label, :alias_json, 1, 0
                )
                """
            ),
            {
                "column_id": column_id,
                "value_text": value_text,
                "display_label": display_label,
                "alias_json": alias_json,
            },
        )
        return int(result.lastrowid)

    async def list_indexable_columns(self) -> list[IndexableColumnRow]:
        """启用表下有效字段，供 ES 向量索引。"""
        result = await self._session.execute(
            text(
                """
                SELECT c.id AS column_id, c.table_id, t.table_name, c.column_name,
                       c.description_manual, c.column_comment_auto, c.alias_json, c.column_role
                FROM copilot_column_meta c
                INNER JOIN copilot_table_meta t ON t.id = c.table_id
                WHERE c.deleted = 0 AND c.status = 1
                  AND t.deleted = 0 AND t.status = 1
                ORDER BY t.table_name, c.ordinal_position, c.column_name
                """
            )
        )
        return [
            IndexableColumnRow(
                column_id=int(r["column_id"]),
                table_id=int(r["table_id"]),
                table_name=str(r["table_name"]),
                column_name=str(r["column_name"]),
                description_manual=r.get("description_manual"),
                column_comment_auto=r.get("column_comment_auto"),
                alias_json=r.get("alias_json"),
                column_role=r.get("column_role"),
            )
            for r in result.mappings().all()
        ]

    async def list_indexable_metrics(self) -> list[IndexableMetricRow]:
        """启用指标，供 ES 向量索引。"""
        result = await self._session.execute(
            text(
                """
                SELECT id AS metric_id, metric_code, metric_name, description,
                       formula_text, relevant_tables, alias_json
                FROM copilot_metric_definition
                WHERE status = 1 AND deleted = 0
                ORDER BY metric_code
                """
            )
        )
        return [
            IndexableMetricRow(
                metric_id=int(r["metric_id"]),
                metric_code=str(r["metric_code"]),
                metric_name=str(r["metric_name"]),
                description=r.get("description"),
                formula_text=r.get("formula_text"),
                relevant_tables=r.get("relevant_tables"),
                alias_json=r.get("alias_json"),
            )
            for r in result.mappings().all()
        ]

    async def list_indexable_field_values(self) -> list[IndexableFieldValueRow]:
        """启用字段取值，供 ES 全文索引。"""
        result = await self._session.execute(
            text(
                """
                SELECT fv.id AS field_value_id, fv.column_id, t.table_name, c.column_name,
                       fv.value_text, fv.display_label, fv.alias_json
                FROM copilot_field_value fv
                INNER JOIN copilot_column_meta c ON c.id = fv.column_id
                INNER JOIN copilot_table_meta t ON t.id = c.table_id
                WHERE fv.deleted = 0 AND fv.status = 1
                  AND c.deleted = 0 AND c.status = 1
                  AND t.deleted = 0 AND t.status = 1
                ORDER BY t.table_name, c.column_name, fv.value_text
                """
            )
        )
        return [
            IndexableFieldValueRow(
                field_value_id=int(r["field_value_id"]),
                column_id=int(r["column_id"]),
                table_name=str(r["table_name"]),
                column_name=str(r["column_name"]),
                value_text=str(r["value_text"]),
                display_label=r.get("display_label"),
                alias_json=r.get("alias_json"),
            )
            for r in result.mappings().all()
        ]


def _map_table(row) -> TableMetaRow:
    return TableMetaRow(
        id=int(row["id"]),
        table_name=str(row["table_name"]),
        table_role=row.get("table_role"),
        biz_domain=row.get("biz_domain"),
        table_comment_auto=row.get("table_comment_auto"),
        description_manual=row.get("description_manual"),
        grain=row.get("grain"),
        sch_id_column=str(row.get("sch_id_column") or "sch_id"),
        last_introspected_at=row.get("last_introspected_at"),
        status=int(row["status"]),
    )


def _map_column(row) -> ColumnMetaRow:
    return ColumnMetaRow(
        id=int(row["id"]),
        table_id=int(row["table_id"]),
        column_name=str(row["column_name"]),
        ordinal_position=int(row["ordinal_position"]),
        data_type=row.get("data_type"),
        column_comment_auto=row.get("column_comment_auto"),
        description_manual=row.get("description_manual"),
        column_role=row.get("column_role"),
        alias_json=row.get("alias_json"),
        is_nullable=int(row["is_nullable"]),
        status=int(row["status"]),
    )


def parse_alias_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def dump_alias_json(aliases: list[str] | None) -> str | None:
    if not aliases:
        return None
    return json.dumps(aliases, ensure_ascii=False)
