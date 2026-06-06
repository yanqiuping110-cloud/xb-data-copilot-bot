"""
元数据业务：introspect 预览、注册表、刷新结构（保护人工定义）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.effective import effective_description
from app.meta.exceptions import MetaError
from app.meta.introspector import BusinessSchemaIntrospector, IntrospectedTable
from app.meta.repository import ColumnMetaRow, MetaRepository, TableMetaRow, dump_alias_json
from config.settings import Settings


@dataclass
class ColumnInput:
    """保存字段时的人工输入。"""

    column_name: str
    description_manual: str | None = None
    column_role: str | None = None
    aliases: list[str] | None = None
    recall_enabled: bool = True


@dataclass
class TableRegisterInput:
    """注册/保存表元数据。"""

    table_name: str
    table_role: str | None = None
    biz_domain: str | None = None
    description_manual: str | None = None
    grain: str | None = None
    sch_id_column: str = "sch_id"
    status: int = 1
    columns: list[ColumnInput] | None = None


class MetaService:
    """元数据编排。"""

    def __init__(
        self,
        copilot_session: AsyncSession,
        business_session: AsyncSession,
        settings: Settings,
    ):
        self._copilot = copilot_session
        self._business = business_session
        self._settings = settings
        self._repo = MetaRepository(copilot_session)
        self._introspector = BusinessSchemaIntrospector(
            business_session, settings.mysql_business_database
        )

    async def introspect_preview(self, table_name: str) -> tuple[IntrospectedTable, bool]:
        """只读预览；返回是否已在 copilot 注册。"""
        snapshot = await self._introspector.introspect_table(table_name)
        existing = await self._repo.find_table_by_name(snapshot.table_name)
        return snapshot, existing is not None

    async def register_table(self, data: TableRegisterInput) -> TableMetaRow:
        """从业务库 introspect 后入库；合并人工 column 输入。"""
        existing = await self._repo.find_table_by_name(data.table_name)
        if existing is not None:
            raise MetaError("TABLE_ALREADY_EXISTS", "该表已在元数据库中注册", 409)

        snapshot = await self._introspector.introspect_table(data.table_name)
        now = datetime.now()
        manual_by_name = {c.column_name: c for c in (data.columns or [])}

        table_id = await self._repo.insert_table(
            table_name=snapshot.table_name,
            table_comment_auto=snapshot.table_comment_auto,
            table_role=data.table_role,
            biz_domain=data.biz_domain,
            description_manual=data.description_manual,
            grain=data.grain,
            sch_id_column=data.sch_id_column,
            last_introspected_at=now,
            status=data.status,
        )

        for col in snapshot.columns:
            inp = manual_by_name.get(col.column_name)
            await self._repo.insert_column(
                table_id=table_id,
                column=col,
                description_manual=inp.description_manual if inp else None,
                column_role=inp.column_role if inp else None,
                alias_json=dump_alias_json(inp.aliases if inp else None),
                recall_enabled=0 if inp and not inp.recall_enabled else 1,
            )

        row = await self._repo.get_table(table_id)
        assert row is not None
        return row

    async def refresh_table_from_business(self, table_id: int) -> TableMetaRow:
        """
        刷新 auto 字段；不覆盖非空 description_manual / alias_json / column_role。
        业务库新增列追加；消失列 status=0。
        """
        table = await self._repo.get_table(table_id)
        if table is None:
            raise MetaError("TABLE_NOT_FOUND", "元数据表不存在", 404)

        snapshot = await self._introspector.introspect_table(table.table_name)
        now = datetime.now()
        await self._repo.update_table_auto_fields(
            table_id,
            table_comment_auto=snapshot.table_comment_auto,
            last_introspected_at=now,
        )

        existing = await self._repo.get_column_map(table_id)
        seen: set[str] = set()

        for col in snapshot.columns:
            seen.add(col.column_name)
            if col.column_name in existing:
                await self._repo.refresh_column_auto(existing[col.column_name].id, col)
            else:
                await self._repo.insert_column(table_id=table_id, column=col)

        for name, row in existing.items():
            if name not in seen and row.status == 1:
                await self._repo.mark_column_inactive(row.id)

        updated = await self._repo.get_table(table_id)
        assert updated is not None
        return updated


def table_to_dict(table: TableMetaRow) -> dict:
    """API 响应用。"""
    return {
        "id": table.id,
        "tableName": table.table_name,
        "tableRole": table.table_role,
        "bizDomain": table.biz_domain,
        "tableCommentAuto": table.table_comment_auto,
        "descriptionManual": table.description_manual,
        "effectiveDescription": effective_description(
            table.description_manual, table.table_comment_auto
        ),
        "grain": table.grain,
        "schIdColumn": table.sch_id_column,
        "lastIntrospectedAt": table.last_introspected_at.isoformat()
        if table.last_introspected_at
        else None,
        "status": table.status,
    }


def column_to_dict(col: ColumnMetaRow) -> dict:
    from app.meta.repository import parse_alias_json

    return {
        "id": col.id,
        "tableId": col.table_id,
        "columnName": col.column_name,
        "ordinalPosition": col.ordinal_position,
        "dataType": col.data_type,
        "columnCommentAuto": col.column_comment_auto,
        "descriptionManual": col.description_manual,
        "effectiveDescription": col.effective_description,
        "columnRole": col.column_role,
        "aliases": parse_alias_json(col.alias_json),
        "isNullable": col.is_nullable == 1,
        "status": col.status,
        "recallEnabled": col.recall_enabled == 1,
    }


def introspect_to_dict(snapshot: IntrospectedTable, exists_in_copilot: bool) -> dict:
    return {
        "tableName": snapshot.table_name,
        "tableCommentAuto": snapshot.table_comment_auto,
        "existsInCopilot": exists_in_copilot,
        "columns": [
            {
                "columnName": c.column_name,
                "dataType": c.data_type,
                "columnCommentAuto": c.column_comment_auto,
                "isNullable": c.is_nullable,
                "ordinalPosition": c.ordinal_position,
            }
            for c in snapshot.columns
        ],
    }
