"""
元数据管理 API 的 Pydantic 模型。
"""

from app.schemas.base import CamelModel


class ColumnManualInput(CamelModel):
    """保存字段时的人工输入。"""

    column_name: str
    description_manual: str | None = None
    column_role: str | None = None
    aliases: list[str] | None = None


class CreateTableMetaRequest(CamelModel):
    """POST /admin/meta/tables：注册业务表。"""

    table_name: str
    table_role: str | None = None
    biz_domain: str | None = None
    description_manual: str | None = None
    grain: str | None = None
    sch_id_column: str = "sch_id"
    status: int = 1
    columns: list[ColumnManualInput] | None = None


class UpdateTableMetaRequest(CamelModel):
    """PUT /admin/meta/tables/{id}。"""

    table_role: str | None = None
    biz_domain: str | None = None
    description_manual: str | None = None
    grain: str | None = None
    sch_id_column: str | None = None
    status: int | None = None


class UpdateColumnMetaRequest(CamelModel):
    """PUT /admin/meta/columns/{id}。"""

    description_manual: str | None = None
    column_role: str | None = None
    aliases: list[str] | None = None


class IntrospectColumnResponse(CamelModel):
    column_name: str
    data_type: str
    column_comment_auto: str | None = None
    is_nullable: bool
    ordinal_position: int


class IntrospectTableResponse(CamelModel):
    table_name: str
    table_comment_auto: str | None = None
    exists_in_copilot: bool
    columns: list[IntrospectColumnResponse]


class TableMetaResponse(CamelModel):
    id: int
    table_name: str
    table_role: str | None = None
    biz_domain: str | None = None
    table_comment_auto: str | None = None
    description_manual: str | None = None
    effective_description: str | None = None
    grain: str | None = None
    sch_id_column: str
    last_introspected_at: str | None = None
    status: int


class ColumnMetaResponse(CamelModel):
    id: int
    table_id: int
    column_name: str
    ordinal_position: int
    data_type: str | None = None
    column_comment_auto: str | None = None
    description_manual: str | None = None
    effective_description: str | None = None
    column_role: str | None = None
    aliases: list[str] = []
    is_nullable: bool
    status: int


class TableMetaListResponse(CamelModel):
    items: list[TableMetaResponse]
    total: int


class RebuildIndexResponse(CamelModel):
    """POST /admin/meta/rebuild-index 响应。"""

    columns: int
    metrics: int
    field_values: int
    embedding_dims: int
