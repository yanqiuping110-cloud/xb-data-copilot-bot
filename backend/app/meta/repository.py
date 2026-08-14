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

# 问数/LLM/工具可见字段：三条件缺一不可（deleted=0 AND status=1 AND recall_enabled=1）


def _ask_column_sql_filter(alias: str = "") -> str:
    """生成 ask 字段过滤 SQL；alias 如 ``c`` → ``c.deleted = 0 AND ...``。"""
    prefix = f"{alias}." if alias else ""
    return (
        f"{prefix}deleted = 0 AND {prefix}status = 1 AND {prefix}recall_enabled = 1"
    )


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
class IndexableTableRow:
    """ES 表级索引一行。"""

    table_id: int
    table_name: str
    table_role: str | None
    biz_domain: str | None
    description_manual: str | None
    table_comment_auto: str | None
    grain: str | None
    column_summary: str | None


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
class IndexableSqlExampleRow:
    """ES L1 样例索引一行。"""

    example_id: int
    question_pattern: str
    description: str | None
    role_scope: str | None
    meta_json: str | None


@dataclass
class RelationRow:
    """copilot_table_relation 一行。"""

    id: int
    from_table_id: int
    from_table_name: str
    from_column: str
    to_table_id: int
    to_table_name: str
    to_column: str
    relation_type: str
    join_hint: str | None
    cardinality: str | None
    status: int


@dataclass
class FieldValueRow:
    """copilot_field_value 一行（含表/字段名）。"""

    id: int
    column_id: int
    table_name: str
    column_name: str
    value_text: str
    display_label: str | None
    alias_json: str | None
    status: int


@dataclass
class MetricRow:
    """copilot_metric_definition 一行。"""

    id: int
    metric_code: str
    metric_name: str
    description: str | None
    sql_template: str | None
    relevant_tables: str | None
    alias_json: str | None
    formula_text: str | None
    filter_hint: str | None
    time_column: str | None
    agg_type: str | None
    unit: str | None
    admin_only: int
    status: int


@dataclass
class MetricColumnLink:
    """指标 ↔ 字段关联。"""

    column_id: int
    table_name: str
    column_name: str
    usage_type: str


@dataclass
class SqlExampleRow:
    """copilot_sql_example 一行。"""

    id: int
    question_pattern: str
    sql_text: str
    meta_json: str | None
    role_scope: str | None
    degrade_priority: int
    description: str | None = None
    source_trace_id: str | None = None
    review_status: int = 1
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None


@dataclass
class BadcaseRow:
    """问数 badcase 记录。"""

    trace_id: str
    question: str
    final_sql: str | None
    status: str
    user_feedback: str | None
    is_badcase: int
    human_corrected_sql: str | None
    created_at: datetime
    role: str | None = None


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
    recall_enabled: int = 1

    @property
    def effective_description(self) -> str | None:
        return effective_description(self.description_manual, self.column_comment_auto)

    @property
    def is_ask_visible(self) -> bool:
        """问数可见（内存判定）：status=1 且 recall_enabled=1。

        deleted=0 由查询层 ``list_recall_columns`` 的 SQL 过滤保证。
        """
        return self.status == 1 and self.recall_enabled == 1


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
        """管理端/同步用：返回表下全部未删除字段（含未参与召回）。"""
        result = await self._session.execute(
            text(
                """
                SELECT id, table_id, column_name, ordinal_position, data_type,
                       column_comment_auto, description_manual, column_role, alias_json,
                       is_nullable, status, recall_enabled
                FROM copilot_column_meta
                WHERE table_id = :table_id AND deleted = 0
                ORDER BY ordinal_position, column_name
                """
            ),
            {"table_id": table_id},
        )
        return [_map_column(r) for r in result.mappings().all()]

    async def list_recall_columns(self, table_id: int) -> list[ColumnMetaRow]:
        """问数/LLM/工具用字段：deleted=0 AND status=1 AND recall_enabled=1。"""
        result = await self._session.execute(
            text(
                f"""
                SELECT id, table_id, column_name, ordinal_position, data_type,
                       column_comment_auto, description_manual, column_role, alias_json,
                       is_nullable, status, recall_enabled
                FROM copilot_column_meta
                WHERE table_id = :table_id
                  AND {_ask_column_sql_filter()}
                ORDER BY ordinal_position, column_name
                """
            ),
            {"table_id": table_id},
        )
        return [_map_column(r) for r in result.mappings().all()]

    async def get_column_map(self, table_id: int) -> dict[str, ColumnMetaRow]:
        cols = await self.list_columns(table_id)
        return {c.column_name: c for c in cols}

    async def get_recall_column_map(self, table_id: int) -> dict[str, ColumnMetaRow]:
        """问数用列名映射（仅 deleted=0 AND status=1 AND recall_enabled=1）。"""
        cols = await self.list_recall_columns(table_id)
        return {c.column_name: c for c in cols}

    async def load_active_column_names(self, table_names: list[str]) -> dict[str, set[str]]:
        """SQL 字段白名单：仅 deleted=0 AND status=1 AND recall_enabled=1。"""
        resolved: dict[str, tuple[str, int]] = {}
        for name in table_names:
            table = await self.find_table_by_name(name)
            if table:
                resolved[name.lower()] = (table.table_name, table.id)

        result: dict[str, set[str]] = {}
        for key, (_table_name, table_id) in resolved.items():
            cols = await self.list_recall_columns(table_id)
            result[key] = {col.column_name for col in cols}
        return result

    async def insert_column(
        self,
        *,
        table_id: int,
        column: IntrospectedColumn,
        description_manual: str | None = None,
        column_role: str | None = None,
        alias_json: str | None = None,
        recall_enabled: int = 1,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_column_meta (
                    table_id, column_name, ordinal_position, data_type, column_comment_auto,
                    description_manual, column_role, alias_json, is_nullable, status,
                    recall_enabled, deleted
                ) VALUES (
                    :table_id, :column_name, :ordinal_position, :data_type, :column_comment_auto,
                    :description_manual, :column_role, :alias_json, :is_nullable, 1,
                    :recall_enabled, 0
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
                "recall_enabled": recall_enabled,
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
                       is_nullable, status, recall_enabled
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
        recall_enabled: int | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_column_meta SET
                    description_manual = COALESCE(:description_manual, description_manual),
                    column_role = COALESCE(:column_role, column_role),
                    alias_json = COALESCE(:alias_json, alias_json),
                    recall_enabled = COALESCE(:recall_enabled, recall_enabled)
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": column_id,
                "description_manual": description_manual,
                "column_role": column_role,
                "alias_json": alias_json,
                "recall_enabled": recall_enabled,
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
        return result

    async def list_indexable_tables(self) -> list[IndexableTableRow]:
        """启用表及其问数字段摘要（字段须 deleted=0 AND status=1 AND recall_enabled=1）。"""
        result = await self._session.execute(
            text(
                f"""
                SELECT t.id AS table_id, t.table_name, t.table_role, t.biz_domain,
                       t.description_manual, t.table_comment_auto, t.grain,
                       GROUP_CONCAT(
                           CONCAT(
                               c.column_name, ' ',
                               COALESCE(NULLIF(TRIM(c.description_manual), ''), c.column_comment_auto, '')
                           )
                           ORDER BY c.ordinal_position, c.column_name
                           SEPARATOR ' '
                       ) AS column_summary
                FROM copilot_table_meta t
                LEFT JOIN copilot_column_meta c
                    ON c.table_id = t.id
                   AND {_ask_column_sql_filter("c")}
                WHERE t.deleted = 0 AND t.status = 1
                GROUP BY t.id, t.table_name, t.table_role, t.biz_domain,
                         t.description_manual, t.table_comment_auto, t.grain
                ORDER BY t.table_name
                """
            )
        )
        rows: list[IndexableTableRow] = []
        for r in result.mappings().all():
            summary = r.get("column_summary")
            if summary and len(summary) > 800:
                summary = summary[:800]
            rows.append(
                IndexableTableRow(
                    table_id=int(r["table_id"]),
                    table_name=str(r["table_name"]),
                    table_role=r.get("table_role"),
                    biz_domain=r.get("biz_domain"),
                    description_manual=r.get("description_manual"),
                    table_comment_auto=r.get("table_comment_auto"),
                    grain=r.get("grain"),
                    column_summary=summary,
                )
            )
        return rows

    async def list_indexable_columns(self) -> list[IndexableColumnRow]:
        """启用表下问数字段（deleted=0 AND status=1 AND recall_enabled=1），供向量索引。"""
        result = await self._session.execute(
            text(
                f"""
                SELECT c.id AS column_id, c.table_id, t.table_name, c.column_name,
                       c.description_manual, c.column_comment_auto, c.alias_json, c.column_role
                FROM copilot_column_meta c
                INNER JOIN copilot_table_meta t ON t.id = c.table_id
                WHERE {_ask_column_sql_filter("c")}
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
        """启用字段取值（所属列须 deleted=0 AND status=1 AND recall_enabled=1），供索引。"""
        result = await self._session.execute(
            text(
                f"""
                SELECT fv.id AS field_value_id, fv.column_id, t.table_name, c.column_name,
                       fv.value_text, fv.display_label, fv.alias_json
                FROM copilot_field_value fv
                INNER JOIN copilot_column_meta c ON c.id = fv.column_id
                INNER JOIN copilot_table_meta t ON t.id = c.table_id
                WHERE fv.deleted = 0 AND fv.status = 1
                  AND {_ask_column_sql_filter("c")}
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

    async def list_indexable_sql_examples(self) -> list[IndexableSqlExampleRow]:
        """已发布 L1 样例，供 ES 向量索引（草稿在索引构建时过滤）。"""
        result = await self._session.execute(
            text(
                """
                SELECT id AS example_id, question_pattern, description, role_scope, meta_json
                FROM copilot_sql_example
                WHERE deleted = 0 AND COALESCE(review_status, 1) = 1
                ORDER BY id
                """
            )
        )
        return [
            IndexableSqlExampleRow(
                example_id=int(r["example_id"]),
                question_pattern=str(r["question_pattern"]),
                description=r.get("description"),
                role_scope=r.get("role_scope"),
                meta_json=r.get("meta_json"),
            )
            for r in result.mappings().all()
        ]

    async def list_relations(self, *, from_table_id: int | None = None) -> list[RelationRow]:
        sql = """
            SELECT r.id, r.from_table_id, ft.table_name AS from_table_name,
                   r.from_column, r.to_table_id, tt.table_name AS to_table_name,
                   r.to_column, r.relation_type, r.join_hint, r.cardinality, r.status
            FROM copilot_table_relation r
            INNER JOIN copilot_table_meta ft ON ft.id = r.from_table_id
            INNER JOIN copilot_table_meta tt ON tt.id = r.to_table_id
            WHERE r.deleted = 0 AND ft.deleted = 0 AND tt.deleted = 0
        """
        params: dict = {}
        if from_table_id is not None:
            sql += " AND r.from_table_id = :from_table_id"
            params["from_table_id"] = from_table_id
        sql += " ORDER BY ft.table_name, r.from_column"
        result = await self._session.execute(text(sql), params)
        return [_map_relation(r) for r in result.mappings().all()]

    async def insert_relation(
        self,
        *,
        from_table_id: int,
        from_column: str,
        to_table_id: int,
        to_column: str,
        relation_type: str = "logical_join",
        join_hint: str | None = None,
        cardinality: str | None = None,
        status: int = 1,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_table_relation (
                    from_table_id, from_column, to_table_id, to_column,
                    relation_type, join_hint, cardinality, status, deleted
                ) VALUES (
                    :from_table_id, :from_column, :to_table_id, :to_column,
                    :relation_type, :join_hint, :cardinality, :status, 0
                )
                """
            ),
            {
                "from_table_id": from_table_id,
                "from_column": from_column,
                "to_table_id": to_table_id,
                "to_column": to_column,
                "relation_type": relation_type,
                "join_hint": join_hint,
                "cardinality": cardinality,
                "status": status,
            },
        )
        return int(result.lastrowid)

    async def update_relation(
        self,
        relation_id: int,
        *,
        from_column: str | None = None,
        to_column: str | None = None,
        relation_type: str | None = None,
        join_hint: str | None = None,
        cardinality: str | None = None,
        status: int | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_table_relation SET
                    from_column = COALESCE(:from_column, from_column),
                    to_column = COALESCE(:to_column, to_column),
                    relation_type = COALESCE(:relation_type, relation_type),
                    join_hint = COALESCE(:join_hint, join_hint),
                    cardinality = COALESCE(:cardinality, cardinality),
                    status = COALESCE(:status, status)
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": relation_id,
                "from_column": from_column,
                "to_column": to_column,
                "relation_type": relation_type,
                "join_hint": join_hint,
                "cardinality": cardinality,
                "status": status,
            },
        )

    async def delete_relation(self, relation_id: int) -> None:
        await self._session.execute(
            text("UPDATE copilot_table_relation SET deleted = 1 WHERE id = :id"),
            {"id": relation_id},
        )

    async def list_field_values(
        self,
        *,
        column_id: int | None = None,
        table_id: int | None = None,
    ) -> list[FieldValueRow]:
        sql = """
            SELECT fv.id, fv.column_id, t.table_name, c.column_name,
                   fv.value_text, fv.display_label, fv.alias_json, fv.status
            FROM copilot_field_value fv
            INNER JOIN copilot_column_meta c ON c.id = fv.column_id
            INNER JOIN copilot_table_meta t ON t.id = c.table_id
            WHERE fv.deleted = 0 AND c.deleted = 0 AND t.deleted = 0
        """
        params: dict = {}
        if column_id is not None:
            sql += " AND fv.column_id = :column_id"
            params["column_id"] = column_id
        if table_id is not None:
            sql += " AND c.table_id = :table_id"
            params["table_id"] = table_id
        sql += " ORDER BY t.table_name, c.column_name, fv.value_text"
        result = await self._session.execute(text(sql), params)
        return [_map_field_value(r) for r in result.mappings().all()]

    async def update_field_value(
        self,
        field_value_id: int,
        *,
        value_text: str | None = None,
        display_label: str | None = None,
        alias_json: str | None = None,
        status: int | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_field_value SET
                    value_text = COALESCE(:value_text, value_text),
                    display_label = COALESCE(:display_label, display_label),
                    alias_json = COALESCE(:alias_json, alias_json),
                    status = COALESCE(:status, status)
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": field_value_id,
                "value_text": value_text,
                "display_label": display_label,
                "alias_json": alias_json,
                "status": status,
            },
        )

    async def delete_field_value(self, field_value_id: int) -> None:
        await self._session.execute(
            text("UPDATE copilot_field_value SET deleted = 1 WHERE id = :id"),
            {"id": field_value_id},
        )

    async def list_metrics(self) -> list[MetricRow]:
        result = await self._session.execute(
            text(
                """
                SELECT id, metric_code, metric_name, description, sql_template,
                       relevant_tables, alias_json, formula_text, filter_hint,
                       time_column, agg_type, unit, admin_only, status
                FROM copilot_metric_definition
                WHERE deleted = 0
                ORDER BY metric_code
                """
            )
        )
        return [_map_metric(r) for r in result.mappings().all()]

    async def get_metric(self, metric_id: int) -> MetricRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, metric_code, metric_name, description, sql_template,
                       relevant_tables, alias_json, formula_text, filter_hint,
                       time_column, agg_type, unit, admin_only, status
                FROM copilot_metric_definition
                WHERE id = :id AND deleted = 0
                """
            ),
            {"id": metric_id},
        )
        row = result.mappings().first()
        return _map_metric(row) if row else None

    async def insert_metric(
        self,
        *,
        metric_code: str,
        metric_name: str,
        description: str | None = None,
        sql_template: str | None = None,
        relevant_tables: str | None = None,
        alias_json: str | None = None,
        formula_text: str | None = None,
        filter_hint: str | None = None,
        time_column: str | None = None,
        agg_type: str | None = None,
        unit: str | None = None,
        admin_only: int = 0,
        status: int = 1,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_metric_definition (
                    metric_code, metric_name, description, sql_template, relevant_tables,
                    alias_json, formula_text, filter_hint, time_column, agg_type, unit,
                    admin_only, status, deleted
                ) VALUES (
                    :metric_code, :metric_name, :description, :sql_template, :relevant_tables,
                    :alias_json, :formula_text, :filter_hint, :time_column, :agg_type, :unit,
                    :admin_only, :status, 0
                )
                """
            ),
            {
                "metric_code": metric_code,
                "metric_name": metric_name,
                "description": description,
                "sql_template": sql_template,
                "relevant_tables": relevant_tables,
                "alias_json": alias_json,
                "formula_text": formula_text,
                "filter_hint": filter_hint,
                "time_column": time_column,
                "agg_type": agg_type,
                "unit": unit,
                "admin_only": admin_only,
                "status": status,
            },
        )
        return int(result.lastrowid)

    async def update_metric(
        self,
        metric_id: int,
        *,
        metric_name: str | None = None,
        description: str | None = None,
        sql_template: str | None = None,
        relevant_tables: str | None = None,
        alias_json: str | None = None,
        formula_text: str | None = None,
        filter_hint: str | None = None,
        time_column: str | None = None,
        agg_type: str | None = None,
        unit: str | None = None,
        admin_only: int | None = None,
        status: int | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_metric_definition SET
                    metric_name = COALESCE(:metric_name, metric_name),
                    description = COALESCE(:description, description),
                    sql_template = COALESCE(:sql_template, sql_template),
                    relevant_tables = COALESCE(:relevant_tables, relevant_tables),
                    alias_json = COALESCE(:alias_json, alias_json),
                    formula_text = COALESCE(:formula_text, formula_text),
                    filter_hint = COALESCE(:filter_hint, filter_hint),
                    time_column = COALESCE(:time_column, time_column),
                    agg_type = COALESCE(:agg_type, agg_type),
                    unit = COALESCE(:unit, unit),
                    admin_only = COALESCE(:admin_only, admin_only),
                    status = COALESCE(:status, status)
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": metric_id,
                "metric_name": metric_name,
                "description": description,
                "sql_template": sql_template,
                "relevant_tables": relevant_tables,
                "alias_json": alias_json,
                "formula_text": formula_text,
                "filter_hint": filter_hint,
                "time_column": time_column,
                "agg_type": agg_type,
                "unit": unit,
                "admin_only": admin_only,
                "status": status,
            },
        )

    async def delete_metric(self, metric_id: int) -> None:
        await self._session.execute(
            text("UPDATE copilot_metric_definition SET deleted = 1 WHERE id = :id"),
            {"id": metric_id},
        )
        await self._session.execute(
            text(
                "UPDATE copilot_metric_column SET deleted = 1 "
                "WHERE metric_id = :id AND deleted = 0"
            ),
            {"id": metric_id},
        )

    async def list_metric_columns(self, metric_id: int) -> list[MetricColumnLink]:
        result = await self._session.execute(
            text(
                """
                SELECT mc.column_id, t.table_name, c.column_name, mc.usage_type
                FROM copilot_metric_column mc
                INNER JOIN copilot_column_meta c ON c.id = mc.column_id
                INNER JOIN copilot_table_meta t ON t.id = c.table_id
                WHERE mc.metric_id = :metric_id AND mc.deleted = 0
                  AND c.deleted = 0 AND t.deleted = 0
                ORDER BY t.table_name, c.column_name
                """
            ),
            {"metric_id": metric_id},
        )
        return [
            MetricColumnLink(
                column_id=int(r["column_id"]),
                table_name=str(r["table_name"]),
                column_name=str(r["column_name"]),
                usage_type=str(r["usage_type"]),
            )
            for r in result.mappings().all()
        ]

    async def replace_metric_columns(
        self,
        metric_id: int,
        links: list[tuple[int, str]],
    ) -> None:
        """全量替换指标字段关联。links: [(column_id, usage_type), ...]"""
        await self._session.execute(
            text(
                "UPDATE copilot_metric_column SET deleted = 1 "
                "WHERE metric_id = :id AND deleted = 0"
            ),
            {"id": metric_id},
        )
        for column_id, usage_type in links:
            await self._session.execute(
                text(
                    """
                    INSERT INTO copilot_metric_column (metric_id, column_id, usage_type, deleted)
                    VALUES (:metric_id, :column_id, :usage_type, 0)
                    ON DUPLICATE KEY UPDATE deleted = 0, usage_type = VALUES(usage_type)
                    """
                ),
                {"metric_id": metric_id, "column_id": column_id, "usage_type": usage_type},
            )

    async def list_sql_examples(self) -> list[SqlExampleRow]:
        result = await self._session.execute(
            text(
                """
                SELECT id, question_pattern, sql_text, description, meta_json, role_scope, degrade_priority,
                       source_trace_id, review_status, reviewed_by, reviewed_at
                FROM copilot_sql_example
                WHERE deleted = 0
                ORDER BY id
                """
            )
        )
        return [_map_sql_example(r) for r in result.mappings().all()]

    async def get_sql_example(self, example_id: int) -> SqlExampleRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, question_pattern, sql_text, description, meta_json, role_scope, degrade_priority,
                       source_trace_id, review_status, reviewed_by, reviewed_at
                FROM copilot_sql_example
                WHERE id = :id AND deleted = 0
                """
            ),
            {"id": example_id},
        )
        row = result.mappings().first()
        return _map_sql_example(row) if row else None

    async def get_sql_examples_by_ids(self, example_ids: list[int]) -> list[SqlExampleRow]:
        if not example_ids:
            return []
        placeholders = ", ".join(f":id{i}" for i in range(len(example_ids)))
        params = {f"id{i}": eid for i, eid in enumerate(example_ids)}
        result = await self._session.execute(
            text(
                f"""
                SELECT id, question_pattern, sql_text, description, meta_json, role_scope, degrade_priority,
                       source_trace_id, review_status, reviewed_by, reviewed_at
                FROM copilot_sql_example
                WHERE deleted = 0 AND id IN ({placeholders})
                """
            ),
            params,
        )
        rows = [_map_sql_example(r) for r in result.mappings().all()]
        order = {eid: idx for idx, eid in enumerate(example_ids)}
        rows.sort(key=lambda r: order.get(r.id, 9999))
        return rows

    async def insert_sql_example(
        self,
        *,
        question_pattern: str,
        sql_text: str,
        description: str | None = None,
        meta_json: str | None = None,
        role_scope: str | None = None,
        degrade_priority: int = 100,
        source_trace_id: str | None = None,
        review_status: int = 1,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_sql_example (
                    question_pattern, sql_text, description, meta_json, role_scope, degrade_priority,
                    source_trace_id, review_status, deleted
                ) VALUES (
                    :question_pattern, :sql_text, :description, :meta_json, :role_scope, :degrade_priority,
                    :source_trace_id, :review_status, 0
                )
                """
            ),
            {
                "question_pattern": question_pattern,
                "sql_text": sql_text,
                "description": description,
                "meta_json": meta_json,
                "role_scope": role_scope,
                "degrade_priority": degrade_priority,
                "source_trace_id": source_trace_id,
                "review_status": review_status,
            },
        )
        return int(result.lastrowid)

    async def publish_sql_example(self, example_id: int, *, reviewed_by: int) -> None:
        """L1 草稿发布：review_status=1，meta_json 去掉 draft。"""
        import json

        row = await self.get_sql_example(example_id)
        if row is None:
            raise ValueError("样例不存在")
        meta: dict = {}
        if row.meta_json:
            try:
                meta = json.loads(row.meta_json)
                if not isinstance(meta, dict):
                    meta = {}
            except json.JSONDecodeError:
                meta = {}
        meta.pop("draft", None)
        await self._session.execute(
            text(
                """
                UPDATE copilot_sql_example SET
                    meta_json = :meta_json,
                    review_status = 1,
                    reviewed_by = :reviewed_by,
                    reviewed_at = NOW()
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": example_id,
                "meta_json": json.dumps(meta, ensure_ascii=False),
                "reviewed_by": reviewed_by,
            },
        )

    async def count_ops_stats(self) -> dict[str, int]:
        """运营看板只读统计。"""
        result = await self._session.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM copilot_ask_turn
                     WHERE deleted = 0 AND (is_badcase = 1 OR user_feedback = 'down')
                       AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS badcase_7d,
                    (SELECT COUNT(*) FROM copilot_glossary_term
                     WHERE deleted = 0 AND status = 1
                       AND updated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) AS glossary_pub_30d,
                    (SELECT COUNT(*) FROM copilot_sql_example
                     WHERE deleted = 0 AND review_status = 1
                       AND reviewed_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) AS l1_pub_30d,
                    (SELECT COUNT(*) FROM copilot_sql_example
                     WHERE deleted = 0 AND review_status = 0) AS l1_draft,
                    (SELECT COUNT(*) FROM copilot_glossary_term
                     WHERE deleted = 0 AND status = 0) AS glossary_draft
                """
            )
        )
        row = result.mappings().first() or {}
        return {
            "badcase_count_7d": int(row.get("badcase_7d") or 0),
            "glossary_published_30d": int(row.get("glossary_pub_30d") or 0),
            "l1_published_30d": int(row.get("l1_pub_30d") or 0),
            "l1_draft_count": int(row.get("l1_draft") or 0),
            "glossary_draft_count": int(row.get("glossary_draft") or 0),
        }

    async def update_sql_example(
        self,
        example_id: int,
        *,
        question_pattern: str | None = None,
        sql_text: str | None = None,
        description: str | None = None,
        meta_json: str | None = None,
        role_scope: str | None = None,
        degrade_priority: int | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_sql_example SET
                    question_pattern = COALESCE(:question_pattern, question_pattern),
                    sql_text = COALESCE(:sql_text, sql_text),
                    description = COALESCE(:description, description),
                    meta_json = COALESCE(:meta_json, meta_json),
                    role_scope = COALESCE(:role_scope, role_scope),
                    degrade_priority = COALESCE(:degrade_priority, degrade_priority)
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": example_id,
                "question_pattern": question_pattern,
                "sql_text": sql_text,
                "description": description,
                "meta_json": meta_json,
                "role_scope": role_scope,
                "degrade_priority": degrade_priority,
            },
        )

    async def delete_sql_example(self, example_id: int) -> None:
        await self._session.execute(
            text("UPDATE copilot_sql_example SET deleted = 1 WHERE id = :id"),
            {"id": example_id},
        )

    async def get_turn_by_trace(self, trace_id: str) -> BadcaseRow | None:
        """按 trace_id 读取问数 turn（badcase 转 L1 等）。"""
        result = await self._session.execute(
            text(
                """
                SELECT trace_id, question, final_sql, status, user_feedback,
                       is_badcase, human_corrected_sql, created_at, role
                FROM copilot_ask_turn
                WHERE trace_id = :trace_id AND deleted = 0
                LIMIT 1
                """
            ),
            {"trace_id": trace_id},
        )
        row = result.mappings().first()
        return _map_badcase(row) if row else None

    async def list_badcases(self, *, limit: int = 50, offset: int = 0) -> list[BadcaseRow]:
        result = await self._session.execute(
            text(
                """
                SELECT trace_id, question, final_sql, status, user_feedback,
                       is_badcase, human_corrected_sql, created_at
                FROM copilot_ask_turn
                WHERE deleted = 0 AND (is_badcase = 1 OR user_feedback = 'down')
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        return [_map_badcase(r) for r in result.mappings().all()]


def _map_relation(row) -> RelationRow:
    return RelationRow(
        id=int(row["id"]),
        from_table_id=int(row["from_table_id"]),
        from_table_name=str(row["from_table_name"]),
        from_column=str(row["from_column"]),
        to_table_id=int(row["to_table_id"]),
        to_table_name=str(row["to_table_name"]),
        to_column=str(row["to_column"]),
        relation_type=str(row["relation_type"]),
        join_hint=row.get("join_hint"),
        cardinality=row.get("cardinality"),
        status=int(row["status"]),
    )


def _map_field_value(row) -> FieldValueRow:
    return FieldValueRow(
        id=int(row["id"]),
        column_id=int(row["column_id"]),
        table_name=str(row["table_name"]),
        column_name=str(row["column_name"]),
        value_text=str(row["value_text"]),
        display_label=row.get("display_label"),
        alias_json=row.get("alias_json"),
        status=int(row["status"]),
    )


def _map_metric(row) -> MetricRow:
    return MetricRow(
        id=int(row["id"]),
        metric_code=str(row["metric_code"]),
        metric_name=str(row["metric_name"]),
        description=row.get("description"),
        sql_template=row.get("sql_template"),
        relevant_tables=row.get("relevant_tables"),
        alias_json=row.get("alias_json"),
        formula_text=row.get("formula_text"),
        filter_hint=row.get("filter_hint"),
        time_column=row.get("time_column"),
        agg_type=row.get("agg_type"),
        unit=row.get("unit"),
        admin_only=int(row.get("admin_only") or 0),
        status=int(row["status"]),
    )


def _map_sql_example(row) -> SqlExampleRow:
    return SqlExampleRow(
        id=int(row["id"]),
        question_pattern=str(row["question_pattern"]),
        sql_text=str(row["sql_text"]),
        description=row.get("description"),
        meta_json=row.get("meta_json"),
        role_scope=row.get("role_scope"),
        degrade_priority=int(row["degrade_priority"]),
        source_trace_id=row.get("source_trace_id"),
        review_status=int(row.get("review_status") or 1),
        reviewed_by=int(row["reviewed_by"]) if row.get("reviewed_by") is not None else None,
        reviewed_at=row.get("reviewed_at"),
    )


def _map_badcase(row) -> BadcaseRow:
    return BadcaseRow(
        trace_id=str(row["trace_id"]),
        question=str(row["question"]),
        final_sql=row.get("final_sql"),
        status=str(row["status"]),
        user_feedback=row.get("user_feedback"),
        is_badcase=int(row["is_badcase"]),
        human_corrected_sql=row.get("human_corrected_sql"),
        created_at=row["created_at"],
        role=row.get("role"),
    )


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
        recall_enabled=int(row.get("recall_enabled", 1)),
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
