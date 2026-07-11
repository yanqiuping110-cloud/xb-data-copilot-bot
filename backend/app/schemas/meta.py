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
    recall_enabled: bool = True


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
    recall_enabled: bool | None = None


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
    recall_enabled: bool = True


class TableMetaListResponse(CamelModel):
    items: list[TableMetaResponse]
    total: int


class RebuildIndexResponse(CamelModel):
    """POST /admin/meta/rebuild-index 响应。"""

    tables: int
    columns: int
    metrics: int
    field_values: int
    embedding_dims: int


class RelationResponse(CamelModel):
    id: int
    from_table_id: int
    from_table_name: str
    from_column: str
    to_table_id: int
    to_table_name: str
    to_column: str
    relation_type: str
    join_hint: str | None = None
    cardinality: str | None = None
    status: int


class CreateRelationRequest(CamelModel):
    from_table_id: int
    from_column: str
    to_table_id: int
    to_column: str
    relation_type: str = "logical_join"
    join_hint: str | None = None
    cardinality: str | None = None
    status: int = 1


class UpdateRelationRequest(CamelModel):
    from_column: str | None = None
    to_column: str | None = None
    relation_type: str | None = None
    join_hint: str | None = None
    cardinality: str | None = None
    status: int | None = None


class FieldValueResponse(CamelModel):
    id: int
    column_id: int
    table_name: str
    column_name: str
    value_text: str
    display_label: str | None = None
    aliases: list[str] = []
    status: int


class CreateFieldValueRequest(CamelModel):
    column_id: int
    value_text: str
    display_label: str | None = None
    aliases: list[str] | None = None
    status: int = 1


class UpdateFieldValueRequest(CamelModel):
    value_text: str | None = None
    display_label: str | None = None
    aliases: list[str] | None = None
    status: int | None = None


class MetricColumnLinkResponse(CamelModel):
    column_id: int
    table_name: str
    column_name: str
    usage_type: str


class MetricResponse(CamelModel):
    id: int
    metric_code: str
    metric_name: str
    description: str | None = None
    sql_template: str | None = None
    relevant_tables: str | None = None
    aliases: list[str] = []
    formula_text: str | None = None
    filter_hint: str | None = None
    time_column: str | None = None
    agg_type: str | None = None
    unit: str | None = None
    admin_only: bool = False
    status: int
    column_links: list[MetricColumnLinkResponse] = []


class MetricColumnInput(CamelModel):
    column_id: int
    usage_type: str = "measure"


class CreateMetricRequest(CamelModel):
    metric_code: str
    metric_name: str
    description: str | None = None
    sql_template: str | None = None
    relevant_tables: str | None = None
    aliases: list[str] | None = None
    formula_text: str | None = None
    filter_hint: str | None = None
    time_column: str | None = None
    agg_type: str | None = None
    unit: str | None = None
    admin_only: bool = False
    status: int = 1
    column_links: list[MetricColumnInput] | None = None


class UpdateMetricRequest(CamelModel):
    metric_name: str | None = None
    description: str | None = None
    sql_template: str | None = None
    relevant_tables: str | None = None
    aliases: list[str] | None = None
    formula_text: str | None = None
    filter_hint: str | None = None
    time_column: str | None = None
    agg_type: str | None = None
    unit: str | None = None
    admin_only: bool | None = None
    status: int | None = None
    column_links: list[MetricColumnInput] | None = None


class SqlExampleResponse(CamelModel):
    id: int
    question_pattern: str
    sql_text: str
    meta_json: dict | None = None
    role_scope: str | None = None
    degrade_priority: int
    source_trace_id: str | None = None
    review_status: int = 1
    reviewed_at: str | None = None


class CreateSqlExampleRequest(CamelModel):
    question_pattern: str
    sql_text: str
    meta_json: dict | None = None
    role_scope: str | None = None
    degrade_priority: int = 100


class UpdateSqlExampleRequest(CamelModel):
    question_pattern: str | None = None
    sql_text: str | None = None
    meta_json: dict | None = None
    role_scope: str | None = None
    degrade_priority: int | None = None


class BadcaseResponse(CamelModel):
    trace_id: str
    question: str
    final_sql: str | None = None
    status: str
    user_feedback: str | None = None
    is_badcase: bool
    human_corrected_sql: str | None = None
    created_at: str


class BadcaseListResponse(CamelModel):
    items: list[BadcaseResponse]
    total: int


class GlossaryTermResponse(CamelModel):
    id: int
    term: str
    canonical_name: str
    definition: str | None = None
    ref_type: str = "concept"
    ref_id: int | None = None
    scope_role: str | None = None
    status: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class GlossaryListResponse(CamelModel):
    items: list[GlossaryTermResponse]
    total: int


class CreateGlossaryRequest(CamelModel):
    term: str
    canonical_name: str
    definition: str | None = None
    ref_type: str = "concept"
    ref_id: int | None = None
    scope_role: str | None = None
    status: int = 0


class UpdateGlossaryRequest(CamelModel):
    term: str | None = None
    canonical_name: str | None = None
    definition: str | None = None
    ref_type: str | None = None
    ref_id: int | None = None
    scope_role: str | None = None
    status: int | None = None


class OpsStatsResponse(CamelModel):
    badcase_count_7d: int
    glossary_published_30d: int
    l1_published_30d: int
    l1_draft_count: int
    glossary_draft_count: int


class GlossarySuggestResponse(CamelModel):
    items: list[dict]
