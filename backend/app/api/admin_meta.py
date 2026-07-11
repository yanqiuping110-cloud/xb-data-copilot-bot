"""
元数据 / 语义库管理 HTTP 接口（ADMIN / OPERATOR）。

路径前缀：/api/v1/admin/meta
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.security import require_meta_manager
from app.db.business import get_business_session
from app.db.copilot import get_copilot_session
from app.meta.repository import MetaRepository, dump_alias_json, parse_alias_json
from app.meta.service import (
    ColumnInput,
    MetaService,
    TableRegisterInput,
    column_to_dict,
    introspect_to_dict,
    table_to_dict,
)
from app.meta.index_service import MetaKnowledgeService
from app.meta.exceptions import MetaError
from app.schemas.meta import (
    BadcaseListResponse,
    BadcaseResponse,
    ColumnMetaResponse,
    CreateFieldValueRequest,
    CreateMetricRequest,
    CreateRelationRequest,
    CreateSqlExampleRequest,
    CreateTableMetaRequest,
    FieldValueResponse,
    IntrospectTableResponse,
    MetricColumnLinkResponse,
    MetricResponse,
    RebuildIndexResponse,
    RelationResponse,
    SqlExampleResponse,
    TableMetaListResponse,
    TableMetaResponse,
    UpdateColumnMetaRequest,
    UpdateFieldValueRequest,
    UpdateMetricRequest,
    UpdateRelationRequest,
    UpdateSqlExampleRequest,
    UpdateTableMetaRequest,
)
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/admin/meta", tags=["admin-meta"])


def _meta_service(
    copilot: AsyncSession,
    business: AsyncSession,
    settings: Settings,
) -> MetaService:
    return MetaService(copilot, business, settings)


def _field_value_response(row) -> FieldValueResponse:
    return FieldValueResponse(
        id=row.id,
        column_id=row.column_id,
        table_name=row.table_name,
        column_name=row.column_name,
        value_text=row.value_text,
        display_label=row.display_label,
        aliases=parse_alias_json(row.alias_json),
        status=row.status,
    )


def _relation_response(row) -> RelationResponse:
    return RelationResponse(
        id=row.id,
        from_table_id=row.from_table_id,
        from_table_name=row.from_table_name,
        from_column=row.from_column,
        to_table_id=row.to_table_id,
        to_table_name=row.to_table_name,
        to_column=row.to_column,
        relation_type=row.relation_type,
        join_hint=row.join_hint,
        cardinality=row.cardinality,
        status=row.status,
    )


async def _metric_response(repo: MetaRepository, metric_id: int) -> MetricResponse:
    row = await repo.get_metric(metric_id)
    if row is None:
        raise MetaError("METRIC_NOT_FOUND", "指标不存在", 404)
    links = await repo.list_metric_columns(metric_id)
    return MetricResponse(
        id=row.id,
        metric_code=row.metric_code,
        metric_name=row.metric_name,
        description=row.description,
        sql_template=row.sql_template,
        relevant_tables=row.relevant_tables,
        aliases=parse_alias_json(row.alias_json),
        formula_text=row.formula_text,
        filter_hint=row.filter_hint,
        time_column=row.time_column,
        agg_type=row.agg_type,
        unit=row.unit,
        admin_only=bool(row.admin_only),
        status=row.status,
        column_links=[
            MetricColumnLinkResponse(
                column_id=lk.column_id,
                table_name=lk.table_name,
                column_name=lk.column_name,
                usage_type=lk.usage_type,
            )
            for lk in links
        ],
    )


def _sql_example_response(row) -> SqlExampleResponse:
    meta = None
    if row.meta_json:
        try:
            meta = json.loads(row.meta_json)
        except json.JSONDecodeError:
            meta = None
    return SqlExampleResponse(
        id=row.id,
        question_pattern=row.question_pattern,
        sql_text=row.sql_text,
        meta_json=meta,
        role_scope=row.role_scope,
        degrade_priority=row.degrade_priority,
        source_trace_id=row.source_trace_id,
        review_status=row.review_status,
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


async def _apply_metric_column_links(
    repo: MetaRepository,
    metric_id: int,
    links: list | None,
) -> None:
    if links is None:
        return
    await repo.replace_metric_columns(
        metric_id,
        [(lk.column_id, lk.usage_type) for lk in links],
    )


@router.get(
    "/introspect/tables/{table_name}",
    response_model=IntrospectTableResponse,
    response_model_by_alias=True,
)
async def introspect_table(
    table_name: str,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    business: Annotated[AsyncSession, Depends(get_business_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IntrospectTableResponse:
    """只读拉取业务库表结构（不落库）。"""
    svc = _meta_service(copilot, business, settings)
    snapshot, exists = await svc.introspect_preview(table_name)
    data = introspect_to_dict(snapshot, exists)
    return IntrospectTableResponse.model_validate(data)


@router.get("/tables", response_model=TableMetaListResponse, response_model_by_alias=True)
async def list_tables(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> TableMetaListResponse:
    repo = MetaRepository(copilot)
    rows = await repo.list_tables(offset=offset, limit=limit)
    return TableMetaListResponse(
        items=[TableMetaResponse.model_validate(table_to_dict(r)) for r in rows],
        total=len(rows),
    )


@router.post(
    "/tables",
    response_model=TableMetaResponse,
    response_model_by_alias=True,
    status_code=201,
)
async def create_table(
    body: CreateTableMetaRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    business: Annotated[AsyncSession, Depends(get_business_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TableMetaResponse:
    """注册业务表：introspect + 合并人工定义后入库。"""
    svc = _meta_service(copilot, business, settings)
    cols = None
    if body.columns:
        cols = [
            ColumnInput(
                column_name=c.column_name,
                description_manual=c.description_manual,
                column_role=c.column_role,
                aliases=c.aliases,
                recall_enabled=c.recall_enabled,
            )
            for c in body.columns
        ]
    row = await svc.register_table(
        TableRegisterInput(
            table_name=body.table_name,
            table_role=body.table_role,
            biz_domain=body.biz_domain,
            description_manual=body.description_manual,
            grain=body.grain,
            sch_id_column=body.sch_id_column,
            status=body.status,
            columns=cols,
        )
    )
    await copilot.commit()
    return TableMetaResponse.model_validate(table_to_dict(row))


@router.get(
    "/tables/{table_id}",
    response_model=TableMetaResponse,
    response_model_by_alias=True,
)
async def get_table(
    table_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> TableMetaResponse:
    repo = MetaRepository(copilot)
    row = await repo.get_table(table_id)
    if row is None:
        from app.meta.exceptions import MetaError

        raise MetaError("TABLE_NOT_FOUND", "元数据表不存在", 404)
    return TableMetaResponse.model_validate(table_to_dict(row))


@router.put(
    "/tables/{table_id}",
    response_model=TableMetaResponse,
    response_model_by_alias=True,
)
async def update_table(
    table_id: int,
    body: UpdateTableMetaRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> TableMetaResponse:
    repo = MetaRepository(copilot)
    existing = await repo.get_table(table_id)
    if existing is None:
        from app.meta.exceptions import MetaError

        raise MetaError("TABLE_NOT_FOUND", "元数据表不存在", 404)
    await repo.update_table_manual_fields(
        table_id,
        table_role=body.table_role,
        biz_domain=body.biz_domain,
        description_manual=body.description_manual,
        grain=body.grain,
        sch_id_column=body.sch_id_column,
        status=body.status,
    )
    await copilot.commit()
    row = await repo.get_table(table_id)
    assert row is not None
    return TableMetaResponse.model_validate(table_to_dict(row))


@router.post(
    "/tables/{table_id}/refresh-from-business",
    response_model=TableMetaResponse,
    response_model_by_alias=True,
)
async def refresh_table(
    table_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    business: Annotated[AsyncSession, Depends(get_business_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TableMetaResponse:
    """刷新 auto 字段；不覆盖非空人工定义。"""
    svc = _meta_service(copilot, business, settings)
    row = await svc.refresh_table_from_business(table_id)
    await copilot.commit()
    return TableMetaResponse.model_validate(table_to_dict(row))


@router.get(
    "/tables/{table_id}/columns",
    response_model=list[ColumnMetaResponse],
    response_model_by_alias=True,
)
async def list_columns(
    table_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> list[ColumnMetaResponse]:
    repo = MetaRepository(copilot)
    if await repo.get_table(table_id) is None:
        from app.meta.exceptions import MetaError

        raise MetaError("TABLE_NOT_FOUND", "元数据表不存在", 404)
    cols = await repo.list_columns(table_id)
    return [ColumnMetaResponse.model_validate(column_to_dict(c)) for c in cols]


@router.put(
    "/columns/{column_id}",
    response_model=ColumnMetaResponse,
    response_model_by_alias=True,
)
async def update_column(
    column_id: int,
    body: UpdateColumnMetaRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> ColumnMetaResponse:
    repo = MetaRepository(copilot)
    existing = await repo.get_column(column_id)
    if existing is None:
        from app.meta.exceptions import MetaError

        raise MetaError("COLUMN_NOT_FOUND", "字段元数据不存在", 404)
    recall_enabled = None
    if body.recall_enabled is not None:
        recall_enabled = 1 if body.recall_enabled else 0
    await repo.update_column_manual(
        column_id,
        description_manual=body.description_manual,
        column_role=body.column_role,
        alias_json=dump_alias_json(body.aliases) if body.aliases is not None else None,
        recall_enabled=recall_enabled,
    )
    await copilot.commit()
    updated = await repo.get_column(column_id)
    assert updated is not None
    return ColumnMetaResponse.model_validate(column_to_dict(updated))


@router.post(
    "/rebuild-index",
    response_model=RebuildIndexResponse,
    response_model_by_alias=True,
)
async def rebuild_search_index(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RebuildIndexResponse:
    """全量重建字段/指标向量索引与字段取值全文索引。"""
    svc = MetaKnowledgeService(copilot, settings)
    try:
        if not await svc.ping_search_index():
            raise MetaError(
                "SEARCH_INDEX_UNAVAILABLE",
                f"检索后端不可用（VECTOR_STORE={settings.vector_store}）",
                503,
            )
        result = await svc.rebuild_all()
    finally:
        await svc.close()
    return RebuildIndexResponse(
        tables=result.tables,
        columns=result.columns,
        metrics=result.metrics,
        field_values=result.field_values,
        embedding_dims=result.embedding_dims,
    )


@router.get("/relations", response_model=list[RelationResponse], response_model_by_alias=True)
async def list_relations(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    from_table_id: int | None = Query(None, alias="fromTableId"),
) -> list[RelationResponse]:
    repo = MetaRepository(copilot)
    rows = await repo.list_relations(from_table_id=from_table_id)
    return [_relation_response(r) for r in rows]


@router.post(
    "/relations",
    response_model=RelationResponse,
    response_model_by_alias=True,
    status_code=201,
)
async def create_relation(
    body: CreateRelationRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> RelationResponse:
    repo = MetaRepository(copilot)
    if await repo.get_table(body.from_table_id) is None:
        raise MetaError("TABLE_NOT_FOUND", "源表不存在", 404)
    if await repo.get_table(body.to_table_id) is None:
        raise MetaError("TABLE_NOT_FOUND", "目标表不存在", 404)
    rid = await repo.insert_relation(
        from_table_id=body.from_table_id,
        from_column=body.from_column,
        to_table_id=body.to_table_id,
        to_column=body.to_column,
        relation_type=body.relation_type,
        join_hint=body.join_hint,
        cardinality=body.cardinality,
        status=body.status,
    )
    await copilot.commit()
    rows = await repo.list_relations()
    row = next((r for r in rows if r.id == rid), None)
    if row is None:
        raise MetaError("RELATION_NOT_FOUND", "关系创建失败", 500)
    return _relation_response(row)


@router.put(
    "/relations/{relation_id}",
    response_model=RelationResponse,
    response_model_by_alias=True,
)
async def update_relation(
    relation_id: int,
    body: UpdateRelationRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> RelationResponse:
    repo = MetaRepository(copilot)
    rows = await repo.list_relations()
    existing = next((r for r in rows if r.id == relation_id), None)
    if existing is None:
        raise MetaError("RELATION_NOT_FOUND", "关系不存在", 404)
    await repo.update_relation(
        relation_id,
        from_column=body.from_column,
        to_column=body.to_column,
        relation_type=body.relation_type,
        join_hint=body.join_hint,
        cardinality=body.cardinality,
        status=body.status,
    )
    await copilot.commit()
    rows = await repo.list_relations()
    row = next((r for r in rows if r.id == relation_id), None)
    assert row is not None
    return _relation_response(row)


@router.delete("/relations/{relation_id}", status_code=204)
async def delete_relation(
    relation_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> None:
    repo = MetaRepository(copilot)
    rows = await repo.list_relations()
    if not any(r.id == relation_id for r in rows):
        raise MetaError("RELATION_NOT_FOUND", "关系不存在", 404)
    await repo.delete_relation(relation_id)
    await copilot.commit()


@router.get(
    "/field-values",
    response_model=list[FieldValueResponse],
    response_model_by_alias=True,
)
async def list_field_values(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    column_id: int | None = Query(None, alias="columnId"),
    table_id: int | None = Query(None, alias="tableId"),
) -> list[FieldValueResponse]:
    repo = MetaRepository(copilot)
    rows = await repo.list_field_values(column_id=column_id, table_id=table_id)
    return [_field_value_response(r) for r in rows]


@router.post(
    "/field-values",
    response_model=FieldValueResponse,
    response_model_by_alias=True,
    status_code=201,
)
async def create_field_value(
    body: CreateFieldValueRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> FieldValueResponse:
    repo = MetaRepository(copilot)
    if await repo.get_column(body.column_id) is None:
        raise MetaError("COLUMN_NOT_FOUND", "字段不存在", 404)
    fid = await repo.upsert_field_value(
        body.column_id,
        value_text=body.value_text,
        display_label=body.display_label,
        alias_json=dump_alias_json(body.aliases),
    )
    if body.status != 1:
        await repo.update_field_value(fid, status=body.status)
    await copilot.commit()
    rows = await repo.list_field_values(column_id=body.column_id)
    row = next((r for r in rows if r.id == fid), None)
    if row is None:
        raise MetaError("FIELD_VALUE_NOT_FOUND", "取值创建失败", 500)
    return _field_value_response(row)


@router.put(
    "/field-values/{field_value_id}",
    response_model=FieldValueResponse,
    response_model_by_alias=True,
)
async def update_field_value(
    field_value_id: int,
    body: UpdateFieldValueRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> FieldValueResponse:
    repo = MetaRepository(copilot)
    rows = await repo.list_field_values()
    existing = next((r for r in rows if r.id == field_value_id), None)
    if existing is None:
        raise MetaError("FIELD_VALUE_NOT_FOUND", "取值不存在", 404)
    await repo.update_field_value(
        field_value_id,
        value_text=body.value_text,
        display_label=body.display_label,
        alias_json=dump_alias_json(body.aliases) if body.aliases is not None else None,
        status=body.status,
    )
    await copilot.commit()
    rows = await repo.list_field_values()
    row = next((r for r in rows if r.id == field_value_id), None)
    assert row is not None
    return _field_value_response(row)


@router.delete("/field-values/{field_value_id}", status_code=204)
async def delete_field_value(
    field_value_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> None:
    repo = MetaRepository(copilot)
    rows = await repo.list_field_values()
    if not any(r.id == field_value_id for r in rows):
        raise MetaError("FIELD_VALUE_NOT_FOUND", "取值不存在", 404)
    await repo.delete_field_value(field_value_id)
    await copilot.commit()


@router.get("/metrics", response_model=list[MetricResponse], response_model_by_alias=True)
async def list_metrics(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> list[MetricResponse]:
    repo = MetaRepository(copilot)
    metrics = await repo.list_metrics()
    result = []
    for m in metrics:
        result.append(await _metric_response(repo, m.id))
    return result


@router.post(
    "/metrics",
    response_model=MetricResponse,
    response_model_by_alias=True,
    status_code=201,
)
async def create_metric(
    body: CreateMetricRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> MetricResponse:
    repo = MetaRepository(copilot)
    mid = await repo.insert_metric(
        metric_code=body.metric_code,
        metric_name=body.metric_name,
        description=body.description,
        sql_template=body.sql_template,
        relevant_tables=body.relevant_tables,
        alias_json=dump_alias_json(body.aliases),
        formula_text=body.formula_text,
        filter_hint=body.filter_hint,
        time_column=body.time_column,
        agg_type=body.agg_type,
        unit=body.unit,
        admin_only=1 if body.admin_only else 0,
        status=body.status,
    )
    await _apply_metric_column_links(repo, mid, body.column_links)
    await copilot.commit()
    return await _metric_response(repo, mid)


@router.put(
    "/metrics/{metric_id}",
    response_model=MetricResponse,
    response_model_by_alias=True,
)
async def update_metric(
    metric_id: int,
    body: UpdateMetricRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> MetricResponse:
    repo = MetaRepository(copilot)
    if await repo.get_metric(metric_id) is None:
        raise MetaError("METRIC_NOT_FOUND", "指标不存在", 404)
    await repo.update_metric(
        metric_id,
        metric_name=body.metric_name,
        description=body.description,
        sql_template=body.sql_template,
        relevant_tables=body.relevant_tables,
        alias_json=dump_alias_json(body.aliases) if body.aliases is not None else None,
        formula_text=body.formula_text,
        filter_hint=body.filter_hint,
        time_column=body.time_column,
        agg_type=body.agg_type,
        unit=body.unit,
        admin_only=(1 if body.admin_only else 0) if body.admin_only is not None else None,
        status=body.status,
    )
    await _apply_metric_column_links(repo, metric_id, body.column_links)
    await copilot.commit()
    return await _metric_response(repo, metric_id)


@router.delete("/metrics/{metric_id}", status_code=204)
async def delete_metric(
    metric_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> None:
    repo = MetaRepository(copilot)
    if await repo.get_metric(metric_id) is None:
        raise MetaError("METRIC_NOT_FOUND", "指标不存在", 404)
    await repo.delete_metric(metric_id)
    await copilot.commit()


@router.get(
    "/sql-examples",
    response_model=list[SqlExampleResponse],
    response_model_by_alias=True,
)
async def list_sql_examples(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> list[SqlExampleResponse]:
    repo = MetaRepository(copilot)
    rows = await repo.list_sql_examples()
    return [_sql_example_response(r) for r in rows]


@router.post(
    "/sql-examples",
    response_model=SqlExampleResponse,
    response_model_by_alias=True,
    status_code=201,
)
async def create_sql_example(
    body: CreateSqlExampleRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> SqlExampleResponse:
    repo = MetaRepository(copilot)
    meta_json = json.dumps(body.meta_json, ensure_ascii=False) if body.meta_json else None
    eid = await repo.insert_sql_example(
        question_pattern=body.question_pattern,
        sql_text=body.sql_text,
        meta_json=meta_json,
        role_scope=body.role_scope,
        degrade_priority=body.degrade_priority,
    )
    await copilot.commit()
    row = await repo.get_sql_example(eid)
    assert row is not None
    return _sql_example_response(row)


@router.put(
    "/sql-examples/{example_id}",
    response_model=SqlExampleResponse,
    response_model_by_alias=True,
)
async def update_sql_example(
    example_id: int,
    body: UpdateSqlExampleRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> SqlExampleResponse:
    repo = MetaRepository(copilot)
    if await repo.get_sql_example(example_id) is None:
        raise MetaError("SQL_EXAMPLE_NOT_FOUND", "L1 样例不存在", 404)
    meta_json = (
        json.dumps(body.meta_json, ensure_ascii=False)
        if body.meta_json is not None
        else None
    )
    await repo.update_sql_example(
        example_id,
        question_pattern=body.question_pattern,
        sql_text=body.sql_text,
        meta_json=meta_json,
        role_scope=body.role_scope,
        degrade_priority=body.degrade_priority,
    )
    await copilot.commit()
    row = await repo.get_sql_example(example_id)
    assert row is not None
    return _sql_example_response(row)


@router.delete("/sql-examples/{example_id}", status_code=204)
async def delete_sql_example(
    example_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> None:
    repo = MetaRepository(copilot)
    if await repo.get_sql_example(example_id) is None:
        raise MetaError("SQL_EXAMPLE_NOT_FOUND", "L1 样例不存在", 404)
    await repo.delete_sql_example(example_id)
    await copilot.commit()


@router.get(
    "/badcases",
    response_model=BadcaseListResponse,
    response_model_by_alias=True,
)
async def list_meta_badcases(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> BadcaseListResponse:
    """badcase 列表（与 /admin/badcases 相同，便于 meta 管理域内访问）。"""
    repo = MetaRepository(copilot)
    rows = await repo.list_badcases(limit=limit, offset=offset)
    items = [
        BadcaseResponse(
            trace_id=r.trace_id,
            question=r.question,
            final_sql=r.final_sql,
            status=r.status,
            user_feedback=r.user_feedback,
            is_badcase=bool(r.is_badcase),
            human_corrected_sql=r.human_corrected_sql,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
    return BadcaseListResponse(items=items, total=len(items))
