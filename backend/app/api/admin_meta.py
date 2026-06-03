"""
元数据 / 语义库管理 HTTP 接口（ADMIN / OPERATOR）。

路径前缀：/api/v1/admin/meta
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.security import require_meta_manager
from app.db.business import get_business_session
from app.db.copilot import get_copilot_session
from app.meta.repository import MetaRepository, dump_alias_json
from app.meta.service import (
    ColumnInput,
    MetaService,
    TableRegisterInput,
    column_to_dict,
    introspect_to_dict,
    table_to_dict,
)
from app.schemas.meta import (
    ColumnMetaResponse,
    CreateTableMetaRequest,
    IntrospectTableResponse,
    TableMetaListResponse,
    TableMetaResponse,
    UpdateColumnMetaRequest,
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
    await repo.update_column_manual(
        column_id,
        description_manual=body.description_manual,
        column_role=body.column_role,
        alias_json=dump_alias_json(body.aliases) if body.aliases is not None else None,
    )
    await copilot.commit()
    updated = await repo.get_column(column_id)
    assert updated is not None
    return ColumnMetaResponse.model_validate(column_to_dict(updated))
