"""空表时从 Settings（env）种子默认 LLM / Embedding / 业务数据源。"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.system.datasource_repository import DatasourceRepository
from app.system.llm_repository import LlmModelRepository
from app.system.runtime_config import refresh_runtime_config
from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def seed_system_config_from_env(
    session: AsyncSession,
    settings: Settings | None = None,
) -> None:
    """
    若对应表无未删除记录，则各插入一条 is_default=1。
    不覆盖用户已配置数据。
    """
    s = settings or get_settings()
    try:
        llm_repo = LlmModelRepository(session, s)
        ds_repo = DatasourceRepository(session, s)
    except Exception:
        logger.warning("system config repos unavailable; skip seed", exc_info=True)
        return

    try:
        if await llm_repo.count_all() == 0:
            chat_extra: dict = {}
            if s.llm_thinking_enabled:
                chat_extra["thinking_enabled"] = True
                if s.llm_reasoning_effort:
                    chat_extra["reasoning_effort"] = s.llm_reasoning_effort
            await llm_repo.insert(
                name="默认 Chat（env）",
                provider="openai_compatible",
                api_base=s.llm_api_base,
                api_key=s.llm_api_key or "ollama",
                model_name=s.llm_model,
                role="chat",
                timeout_sec=s.llm_timeout_sec,
                temperature=0.0,
                extra=chat_extra,
                is_default=True,
                status=1,
            )
            await llm_repo.insert(
                name="默认 Embedding（env）",
                provider="openai_compatible",
                api_base=s.embedding_api_base,
                api_key=s.embedding_api_key or "ollama",
                model_name=s.embedding_model,
                role="embedding",
                timeout_sec=s.llm_timeout_sec,
                temperature=0.0,
                extra={"embedding_dims": s.embedding_dims},
                is_default=True,
                status=1,
            )
            logger.info("seeded default chat + embedding models from env")

        if await ds_repo.count_all() == 0:
            await ds_repo.insert(
                name="默认业务库（env）",
                db_type="mysql",
                host=s.mysql_business_host,
                port=s.mysql_business_port,
                database_name=s.mysql_business_database,
                username=s.mysql_business_user,
                password=s.mysql_business_password,
                is_default=True,
                status=1,
            )
            logger.info("seeded default business datasource from env")

        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("seed_system_config_from_env failed (table missing?)", exc_info=True)
        return

    await refresh_runtime_config(session, s)
