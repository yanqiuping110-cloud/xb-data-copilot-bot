"""
运行时配置解析：库内默认优先，否则回退 Settings（env）。

进程内缓存；启动种子与 Admin 写操作后调用 refresh_runtime_config。
同步 resolve_* 供 build_llm / EmbeddingClient / business 引擎使用。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.system.datasource_repository import DatasourceRepository
from app.system.llm_repository import LlmModelRepository
from app.system.models import ResolvedBusinessDsn, ResolvedLlmConfig
from app.system.param_repository import SysParamRepository
from app.system.param_specs import PARAM_SQL_MAX_ROWS, clamp_sql_max_rows
from config.settings import Settings, get_settings

# 确保连接器已注册
import app.system.connectors  # noqa: F401

logger = logging.getLogger(__name__)

_chat: ResolvedLlmConfig | None = None
_embedding: ResolvedLlmConfig | None = None
_business: ResolvedBusinessDsn | None = None
_sql_max_rows: int | None = None


def _env_chat(settings: Settings) -> ResolvedLlmConfig:
    extra: dict[str, Any] = {}
    if settings.llm_thinking_enabled:
        extra["thinking_enabled"] = True
        if settings.llm_reasoning_effort:
            extra["reasoning_effort"] = settings.llm_reasoning_effort
    return ResolvedLlmConfig(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key or "ollama",
        model=settings.llm_model,
        timeout_sec=settings.llm_timeout_sec,
        temperature=0.0,
        extra=extra,
        source="env",
        name="env-chat",
    )


def _env_embedding(settings: Settings) -> ResolvedLlmConfig:
    return ResolvedLlmConfig(
        api_base=settings.embedding_api_base,
        api_key=settings.embedding_api_key or "ollama",
        model=settings.embedding_model,
        timeout_sec=settings.llm_timeout_sec,
        temperature=0.0,
        extra={"embedding_dims": settings.embedding_dims},
        source="env",
        name="env-embedding",
    )


def _env_business(settings: Settings) -> ResolvedBusinessDsn:
    return ResolvedBusinessDsn(
        host=settings.mysql_business_host,
        port=settings.mysql_business_port,
        user=settings.mysql_business_user,
        password=settings.mysql_business_password,
        database=settings.mysql_business_database,
        db_type="mysql",
        source="env",
        name="env-business",
    )


def resolve_chat_llm(settings: Settings | None = None) -> ResolvedLlmConfig:
    """同步读取生效 chat 配置（缓存 miss 时回退 env）。"""
    global _chat
    if _chat is not None:
        return _chat
    s = settings or get_settings()
    return _env_chat(s)


def resolve_embedding(settings: Settings | None = None) -> ResolvedLlmConfig:
    global _embedding
    if _embedding is not None:
        return _embedding
    s = settings or get_settings()
    return _env_embedding(s)


def resolve_business_dsn(settings: Settings | None = None) -> ResolvedBusinessDsn:
    global _business
    if _business is not None:
        return _business
    s = settings or get_settings()
    return _env_business(s)


def _env_sql_max_rows(settings: Settings) -> int:
    return clamp_sql_max_rows(int(getattr(settings, "sql_max_rows", 100) or 100))


def resolve_sql_max_rows(settings: Settings | None = None) -> int:
    """同步读取生效的问数 SQL LIMIT（缓存 miss 时回退 env / 默认 100）。"""
    global _sql_max_rows
    if _sql_max_rows is not None:
        return _sql_max_rows
    s = settings or get_settings()
    return _env_sql_max_rows(s)


def invalidate_runtime_cache() -> None:
    """清空进程缓存（随后 resolve 暂回退 env，直至 refresh）。"""
    global _chat, _embedding, _business, _sql_max_rows
    _chat = None
    _embedding = None
    _business = None
    _sql_max_rows = None


async def refresh_runtime_config(
    session: AsyncSession,
    settings: Settings | None = None,
) -> None:
    """从 copilot 库加载默认配置写入缓存；无记录则用 env。"""
    global _chat, _embedding, _business, _sql_max_rows
    s = settings or get_settings()
    try:
        llm_repo = LlmModelRepository(session, s)
        ds_repo = DatasourceRepository(session, s)

        chat_row = await llm_repo.get_default("chat")
        if chat_row is not None:
            extra = dict(chat_row.extra)
            _chat = ResolvedLlmConfig(
                api_base=chat_row.api_base,
                api_key=chat_row.decrypt_api_key(s) or "ollama",
                model=chat_row.model_name,
                timeout_sec=chat_row.timeout_sec,
                temperature=chat_row.temperature,
                extra=extra,
                source="db",
                name=chat_row.name,
                model_id=chat_row.id,
                provider=chat_row.provider,
            )
        else:
            _chat = _env_chat(s)

        emb_row = await llm_repo.get_default("embedding")
        if emb_row is not None:
            extra = dict(emb_row.extra)
            if "embedding_dims" not in extra:
                extra["embedding_dims"] = s.embedding_dims
            _embedding = ResolvedLlmConfig(
                api_base=emb_row.api_base,
                api_key=emb_row.decrypt_api_key(s) or "ollama",
                model=emb_row.model_name,
                timeout_sec=emb_row.timeout_sec,
                temperature=0.0,
                extra=extra,
                source="db",
                name=emb_row.name,
                model_id=emb_row.id,
                provider=emb_row.provider,
            )
        else:
            _embedding = _env_embedding(s)

        ds_row = await ds_repo.get_default()
        if ds_row is not None:
            _business = ResolvedBusinessDsn(
                host=ds_row.host,
                port=ds_row.port,
                user=ds_row.username,
                password=ds_row.decrypt_password(s),
                database=ds_row.database_name,
                db_type=ds_row.db_type or "mysql",
                server_version=ds_row.server_version,
                options=ds_row.options(),
                source="db",
                name=ds_row.name,
                datasource_id=ds_row.id,
            )
        else:
            _business = _env_business(s)
    except Exception:
        # 表未建或库不可用：Fail-open 到 env
        logger.warning("refresh_runtime_config failed; falling back to env", exc_info=True)
        _chat = _env_chat(s)
        _embedding = _env_embedding(s)
        _business = _env_business(s)

    try:
        param_repo = SysParamRepository(session)
        param_row = await param_repo.get_by_key(PARAM_SQL_MAX_ROWS)
        if param_row is not None:
            try:
                _sql_max_rows = clamp_sql_max_rows(int(str(param_row.param_value).strip()))
            except (TypeError, ValueError):
                _sql_max_rows = _env_sql_max_rows(s)
        else:
            _sql_max_rows = _env_sql_max_rows(s)
    except Exception:
        logger.warning("sys_param load failed; using env SQL_MAX_ROWS", exc_info=True)
        _sql_max_rows = _env_sql_max_rows(s)
