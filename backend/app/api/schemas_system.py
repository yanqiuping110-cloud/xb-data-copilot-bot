"""系统配置 Admin API 的请求/响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.base import CamelModel


class LlmModelResponse(CamelModel):
    id: int
    name: str
    provider: str
    api_base: str
    model_name: str
    role: str
    timeout_sec: int
    temperature: float
    extra: dict[str, Any] = Field(default_factory=dict)
    is_default: bool
    status: int
    has_api_key: bool
    created_at: str | None = None
    updated_at: str | None = None


class LlmModelListResponse(CamelModel):
    items: list[LlmModelResponse]


class CreateLlmModelRequest(CamelModel):
    name: str
    provider: str = "openai_compatible"
    api_base: str
    api_key: str | None = None
    model_name: str
    role: str
    timeout_sec: int = 120
    temperature: float = 0.0
    extra: dict[str, Any] | None = None
    is_default: bool = False
    status: int = 1


class UpdateLlmModelRequest(CamelModel):
    name: str | None = None
    provider: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    timeout_sec: int | None = None
    temperature: float | None = None
    extra: dict[str, Any] | None = None
    status: int | None = None


class TestResultResponse(CamelModel):
    ok: bool
    message: str
    server_version: str | None = None


class DatasourceResponse(CamelModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    is_default: bool
    status: int
    has_password: bool
    last_test_at: str | None = None
    last_test_ok: bool | None = None
    server_version: str | None = None
    version_checked_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DatasourceListResponse(CamelModel):
    items: list[DatasourceResponse]


class CreateDatasourceRequest(CamelModel):
    name: str
    db_type: str = "mysql"
    host: str
    port: int = 3306
    database_name: str
    username: str
    password: str | None = None
    is_default: bool = False
    status: int = 1


class UpdateDatasourceRequest(CamelModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    status: int | None = None


class TestDatasourceRequest(CamelModel):
    """未保存连接也可测试。"""

    host: str
    port: int = 3306
    database_name: str
    username: str
    password: str = ""
    db_type: str = "mysql"


class LlmProviderCatalogItem(CamelModel):
    code: str
    name: str
    logo_key: str = ""
    color: str = "#0CA678"
    default_api_base: str = ""
    suggested_models: list[str] = Field(default_factory=list)
    supports_thinking: bool = False
    adapter_key: str = "openai_compatible"
    extra_defaults: dict[str, Any] = Field(default_factory=dict)
    roles: list[str] = Field(default_factory=list)


class LlmProviderCatalogResponse(CamelModel):
    items: list[LlmProviderCatalogItem]


class DatasourceTypeCatalogItem(CamelModel):
    code: str
    name: str
    group: str = "oltp"
    status: str = "coming_soon"
    selectable: bool = False
    color: str = "#0CA678"
    default_port: int = 0
    version_hint: str = ""
    dialect: str = ""
    sqlglot_read: str = ""
    form_schema: list[dict[str, Any]] = Field(default_factory=list)


class DatasourceTypeCatalogResponse(CamelModel):
    items: list[DatasourceTypeCatalogItem]
