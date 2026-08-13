"""
系统管理：AI 模型 + 业务数据源 + 系统参数（仅 ADMIN）。

对标 SQLBot 系统管理 / 数据源；运行时经 runtime_config 生效。
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_system import (
    CreateDatasourceRequest,
    CreateLlmModelRequest,
    DatasourceListResponse,
    DatasourceResponse,
    DatasourceTypeCatalogItem,
    DatasourceTypeCatalogResponse,
    LlmModelListResponse,
    LlmModelResponse,
    LlmProviderCatalogItem,
    LlmProviderCatalogResponse,
    SysParamListResponse,
    SysParamResponse,
    TestDatasourceRequest,
    TestResultResponse,
    UpdateDatasourceRequest,
    UpdateLlmModelRequest,
    UpdateSysParamRequest,
)
from app.core.context import UserContext
from app.core.security import require_admin
from app.db.business import invalidate_business_engine
from app.db.copilot import get_copilot_session
from app.system.audit import log_system_config_event
from app.system.catalog_loader import (
    get_datasource_type,
    has_llm_provider,
    is_datasource_selectable,
    list_datasource_types,
    list_llm_providers,
)
from app.system.datasource_repository import DatasourceRepository, DatasourceRow
from app.system.exceptions import SystemConfigError
from app.system.llm_repository import LlmModelRepository, LlmModelRow
from app.system.param_repository import SysParamRepository, require_spec
from app.system.param_specs import SYS_PARAM_SPECS
from app.system.runtime_config import refresh_runtime_config
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/admin/system", tags=["admin-system"])


def _iso(dt) -> str | None:
    return dt.isoformat(sep=" ", timespec="seconds") if dt else None


def _llm_response(row: LlmModelRow) -> LlmModelResponse:
    return LlmModelResponse(
        id=row.id,
        name=row.name,
        provider=row.provider,
        api_base=row.api_base,
        model_name=row.model_name,
        role=row.role,
        timeout_sec=row.timeout_sec,
        temperature=row.temperature,
        extra=row.extra,
        is_default=row.is_default == 1,
        status=row.status,
        has_api_key=row.has_api_key,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


def _ds_response(row: DatasourceRow) -> DatasourceResponse:
    return DatasourceResponse(
        id=row.id,
        name=row.name,
        db_type=row.db_type,
        host=row.host,
        port=row.port,
        database_name=row.database_name,
        username=row.username,
        is_default=row.is_default == 1,
        status=row.status,
        has_password=row.has_password,
        last_test_at=_iso(row.last_test_at),
        last_test_ok=None if row.last_test_ok is None else bool(row.last_test_ok),
        server_version=row.server_version,
        version_checked_at=_iso(row.version_checked_at),
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


# ---------- Catalog ----------


@router.get(
    "/llm-providers",
    response_model=LlmProviderCatalogResponse,
    response_model_by_alias=True,
)
async def get_llm_provider_catalog(
    _: Annotated[UserContext, Depends(require_admin)],
) -> LlmProviderCatalogResponse:
    items = [
        LlmProviderCatalogItem(
            code=str(p.get("code", "")),
            name=str(p.get("name", "")),
            logo_key=str(p.get("logoKey") or p.get("logo_key") or ""),
            color=str(p.get("color") or "#0CA678"),
            default_api_base=str(p.get("defaultApiBase") or p.get("default_api_base") or ""),
            suggested_models=list(p.get("suggestedModels") or p.get("suggested_models") or []),
            supports_thinking=bool(p.get("supportsThinking") or p.get("supports_thinking")),
            adapter_key=str(p.get("adapterKey") or p.get("adapter_key") or "openai_compatible"),
            extra_defaults=dict(p.get("extraDefaults") or p.get("extra_defaults") or {}),
            roles=list(p.get("roles") or []),
        )
        for p in list_llm_providers()
    ]
    return LlmProviderCatalogResponse(items=items)


@router.get(
    "/datasource-types",
    response_model=DatasourceTypeCatalogResponse,
    response_model_by_alias=True,
)
async def get_datasource_type_catalog(
    _: Annotated[UserContext, Depends(require_admin)],
) -> DatasourceTypeCatalogResponse:
    from app.system.connectors import registry

    items = []
    for t in list_datasource_types():
        code = str(t.get("code", ""))
        catalog_selectable = bool(t.get("selectable"))
        available = registry.is_available(code)
        selectable = catalog_selectable and available
        status = str(t.get("status") or "coming_soon")
        if catalog_selectable and not available:
            status = "coming_soon"
        items.append(
            DatasourceTypeCatalogItem(
                code=code,
                name=str(t.get("name", "")),
                group=str(t.get("group") or "oltp"),
                status=status,
                selectable=selectable,
                color=str(t.get("color") or "#0CA678"),
                default_port=int(t.get("defaultPort") or t.get("default_port") or 0),
                version_hint=str(t.get("versionHint") or t.get("version_hint") or ""),
                dialect=str(t.get("dialect") or ""),
                sqlglot_read=str(t.get("sqlglotRead") or t.get("sqlglot_read") or ""),
                form_schema=list(t.get("formSchema") or t.get("form_schema") or []),
            )
        )
    return DatasourceTypeCatalogResponse(items=items)


# ---------- LLM ----------


@router.get("/llm-models", response_model=LlmModelListResponse, response_model_by_alias=True)
async def list_llm_models(
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    role: Annotated[str | None, Query()] = None,
) -> LlmModelListResponse:
    repo = LlmModelRepository(session, settings)
    items = await repo.list_models(role=role)
    return LlmModelListResponse(items=[_llm_response(r) for r in items])


@router.post("/llm-models", response_model=LlmModelResponse, response_model_by_alias=True)
async def create_llm_model(
    body: CreateLlmModelRequest,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LlmModelResponse:
    provider = (body.provider or "openai_compatible").strip()
    if not has_llm_provider(provider):
        raise SystemConfigError("UNKNOWN_LLM_PROVIDER", f"未知供应商：{provider}", 400)
    repo = LlmModelRepository(session, settings)
    model_id = await repo.insert(
        name=body.name.strip(),
        provider=provider,
        api_base=body.api_base.strip(),
        api_key=body.api_key,
        model_name=body.model_name.strip(),
        role=body.role.strip(),
        timeout_sec=body.timeout_sec,
        temperature=body.temperature,
        extra=body.extra,
        is_default=body.is_default,
        status=body.status,
    )
    await log_system_config_event(
        session, ctx=ctx, action="llm.create", detail=f"id={model_id} role={body.role}"
    )
    await session.commit()
    await refresh_runtime_config(session, settings)
    row = await repo.get(model_id)
    assert row is not None
    return _llm_response(row)


@router.put("/llm-models/{model_id}", response_model=LlmModelResponse, response_model_by_alias=True)
async def update_llm_model(
    model_id: int,
    body: UpdateLlmModelRequest,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LlmModelResponse:
    if body.provider is not None and not has_llm_provider(body.provider.strip()):
        raise SystemConfigError(
            "UNKNOWN_LLM_PROVIDER", f"未知供应商：{body.provider}", 400
        )
    repo = LlmModelRepository(session, settings)
    await repo.update(
        model_id,
        name=body.name.strip() if body.name is not None else None,
        provider=body.provider.strip() if body.provider is not None else None,
        api_base=body.api_base.strip() if body.api_base is not None else None,
        api_key=body.api_key,
        model_name=body.model_name.strip() if body.model_name is not None else None,
        timeout_sec=body.timeout_sec,
        temperature=body.temperature,
        extra=body.extra,
        status=body.status,
    )
    await log_system_config_event(
        session, ctx=ctx, action="llm.update", detail=f"id={model_id}"
    )
    await session.commit()
    await refresh_runtime_config(session, settings)
    row = await repo.get(model_id)
    assert row is not None
    return _llm_response(row)


@router.delete("/llm-models/{model_id}", status_code=204)
async def delete_llm_model(
    model_id: int,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    repo = LlmModelRepository(session, settings)
    await repo.soft_delete(model_id)
    await log_system_config_event(
        session, ctx=ctx, action="llm.delete", detail=f"id={model_id}"
    )
    await session.commit()
    await refresh_runtime_config(session, settings)


@router.post(
    "/llm-models/{model_id}/set-default",
    response_model=LlmModelResponse,
    response_model_by_alias=True,
)
async def set_default_llm_model(
    model_id: int,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LlmModelResponse:
    repo = LlmModelRepository(session, settings)
    row = await repo.set_default(model_id)
    await log_system_config_event(
        session,
        ctx=ctx,
        action="llm.set_default",
        detail=f"id={model_id} role={row.role} name={row.name}",
    )
    await session.commit()
    await refresh_runtime_config(session, settings)
    return _llm_response(row)


@router.post(
    "/llm-models/{model_id}/test",
    response_model=TestResultResponse,
    response_model_by_alias=True,
)
async def test_llm_model(
    model_id: int,
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestResultResponse:
    repo = LlmModelRepository(session, settings)
    row = await repo.get(model_id)
    if row is None:
        raise SystemConfigError("LLM_NOT_FOUND", "模型不存在", 404)
    api_key = row.decrypt_api_key(settings) or "ollama"
    base = row.api_base.rstrip("/")
    try:
        timeout = httpx.Timeout(min(row.timeout_sec, 30))
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            if row.role == "embedding":
                resp = await client.post(
                    f"{base}/embeddings",
                    headers=headers,
                    json={"model": row.model_name, "input": ["ping"]},
                )
            else:
                resp = await client.post(
                    f"{base}/chat/completions",
                    headers=headers,
                    json={
                        "model": row.model_name,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 8,
                    },
                )
            if resp.status_code >= 400:
                return TestResultResponse(
                    ok=False, message=f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
        return TestResultResponse(ok=True, message="连通成功")
    except Exception as e:
        return TestResultResponse(ok=False, message=str(e)[:300])


# ---------- Datasource ----------


@router.get("/datasources", response_model=DatasourceListResponse, response_model_by_alias=True)
async def list_datasources(
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DatasourceListResponse:
    repo = DatasourceRepository(session, settings)
    items = await repo.list_all()
    return DatasourceListResponse(items=[_ds_response(r) for r in items])


@router.post("/datasources", response_model=DatasourceResponse, response_model_by_alias=True)
async def create_datasource(
    body: CreateDatasourceRequest,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DatasourceResponse:
    db_type = (body.db_type or "mysql").strip()
    if not is_datasource_selectable(db_type):
        meta = get_datasource_type(db_type)
        label = (meta or {}).get("name") or db_type
        raise SystemConfigError(
            "UNSUPPORTED_DB_TYPE",
            f"数据源类型「{label}」暂不可用",
            400,
        )
    repo = DatasourceRepository(session, settings)
    ds_id = await repo.insert(
        name=body.name.strip(),
        db_type=db_type,
        host=body.host.strip(),
        port=body.port,
        database_name=body.database_name.strip(),
        username=body.username.strip(),
        password=body.password,
        is_default=body.is_default,
        status=body.status,
    )
    await log_system_config_event(
        session, ctx=ctx, action="datasource.create", detail=f"id={ds_id}"
    )
    await session.commit()
    if body.is_default:
        await refresh_runtime_config(session, settings)
        await invalidate_business_engine()
    else:
        await refresh_runtime_config(session, settings)
    row = await repo.get(ds_id)
    assert row is not None
    return _ds_response(row)


@router.put(
    "/datasources/{ds_id}",
    response_model=DatasourceResponse,
    response_model_by_alias=True,
)
async def update_datasource(
    ds_id: int,
    body: UpdateDatasourceRequest,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DatasourceResponse:
    repo = DatasourceRepository(session, settings)
    before = await repo.get(ds_id)
    await repo.update(
        ds_id,
        name=body.name.strip() if body.name is not None else None,
        host=body.host.strip() if body.host is not None else None,
        port=body.port,
        database_name=body.database_name.strip() if body.database_name is not None else None,
        username=body.username.strip() if body.username is not None else None,
        password=body.password,
        status=body.status,
    )
    await log_system_config_event(
        session, ctx=ctx, action="datasource.update", detail=f"id={ds_id}"
    )
    await session.commit()
    await refresh_runtime_config(session, settings)
    if before and before.is_default == 1:
        await invalidate_business_engine()
    row = await repo.get(ds_id)
    assert row is not None
    return _ds_response(row)


@router.delete("/datasources/{ds_id}", status_code=204)
async def delete_datasource(
    ds_id: int,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    repo = DatasourceRepository(session, settings)
    await repo.soft_delete(ds_id)
    await log_system_config_event(
        session, ctx=ctx, action="datasource.delete", detail=f"id={ds_id}"
    )
    await session.commit()
    await refresh_runtime_config(session, settings)


@router.post(
    "/datasources/{ds_id}/set-default",
    response_model=DatasourceResponse,
    response_model_by_alias=True,
)
async def set_default_datasource(
    ds_id: int,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DatasourceResponse:
    repo = DatasourceRepository(session, settings)
    row = await repo.set_default(ds_id)
    await log_system_config_event(
        session,
        ctx=ctx,
        action="datasource.set_default",
        detail=f"id={ds_id} name={row.name} db={row.database_name}",
    )
    await session.commit()
    await refresh_runtime_config(session, settings)
    await invalidate_business_engine()
    return _ds_response(row)


async def _probe_datasource(
    *,
    db_type: str,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> TestResultResponse:
    from app.system.connectors import registry
    from app.system.connectors.base import ConnectParams

    try:
        connector = registry.require(db_type)
    except LookupError as e:
        raise SystemConfigError("UNSUPPORTED_DB_TYPE", str(e), 400) from e
    result = await connector.probe(
        ConnectParams(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password or "",
        )
    )
    return TestResultResponse(
        ok=result.ok,
        message=result.message,
        server_version=result.server_version,
    )


@router.post("/datasources/test", response_model=TestResultResponse, response_model_by_alias=True)
async def test_datasource_draft(
    body: TestDatasourceRequest,
    _: Annotated[UserContext, Depends(require_admin)],
) -> TestResultResponse:
    if not is_datasource_selectable(body.db_type):
        meta = get_datasource_type(body.db_type)
        label = (meta or {}).get("name") or body.db_type
        raise SystemConfigError(
            "UNSUPPORTED_DB_TYPE",
            f"数据源类型「{label}」暂不可用",
            400,
        )
    return await _probe_datasource(
        db_type=body.db_type,
        host=body.host.strip(),
        port=body.port,
        database=body.database_name.strip(),
        user=body.username.strip(),
        password=body.password or "",
    )


@router.post(
    "/datasources/{ds_id}/test",
    response_model=TestResultResponse,
    response_model_by_alias=True,
)
async def test_datasource_saved(
    ds_id: int,
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestResultResponse:
    repo = DatasourceRepository(session, settings)
    row = await repo.get(ds_id)
    if row is None:
        raise SystemConfigError("DATASOURCE_NOT_FOUND", "数据源不存在", 404)
    result = await _probe_datasource(
        db_type=row.db_type,
        host=row.host,
        port=row.port,
        database=row.database_name,
        user=row.username,
        password=row.decrypt_password(settings),
    )
    await repo.update_test_result(
        ds_id,
        ok=result.ok,
        server_version=result.server_version if result.ok else None,
    )
    await session.commit()
    if result.ok and row.is_default == 1:
        await refresh_runtime_config(session, settings)
    return result


def _sys_param_response(spec, db_value: str | None, updated_at) -> SysParamResponse:
    return SysParamResponse(
        key=spec.key,
        value=db_value if db_value is not None else spec.default,
        value_type=spec.value_type,
        display_name=spec.display_name,
        description=spec.description or "",
        min_value=spec.min_value,
        max_value=spec.max_value,
        updated_at=_iso(updated_at) if updated_at else None,
    )


@router.get("/params", response_model=SysParamListResponse, response_model_by_alias=True)
async def list_sys_params(
    _ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> SysParamListResponse:
    repo = SysParamRepository(session)
    try:
        rows = {r.param_key: r for r in await repo.list_all()}
    except Exception as exc:
        raise SystemConfigError(
            "SYS_PARAM_UNAVAILABLE",
            "系统参数表未就绪，请先执行 V018__sys_param.sql",
            503,
        ) from exc
    items = []
    for spec in SYS_PARAM_SPECS.values():
        row = rows.get(spec.key)
        items.append(
            _sys_param_response(
                spec,
                row.param_value if row else None,
                row.updated_at if row else None,
            )
        )
    return SysParamListResponse(items=items)


@router.put(
    "/params/{param_key}",
    response_model=SysParamResponse,
    response_model_by_alias=True,
)
async def update_sys_param(
    param_key: str,
    body: UpdateSysParamRequest,
    ctx: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SysParamResponse:
    spec = require_spec(param_key)
    repo = SysParamRepository(session)
    try:
        row = await repo.upsert(
            spec=spec,
            value=body.value,
            updated_by=ctx.user_id,
        )
    except SystemConfigError:
        raise
    except Exception as exc:
        raise SystemConfigError(
            "SYS_PARAM_UNAVAILABLE",
            "系统参数表未就绪，请先执行 V018__sys_param.sql",
            503,
        ) from exc
    await log_system_config_event(
        session,
        ctx=ctx,
        action="sys_param.update",
        detail=f"{param_key}={row.param_value}",
    )
    await session.commit()
    await refresh_runtime_config(session, settings)
    return _sys_param_response(spec, row.param_value, row.updated_at)
