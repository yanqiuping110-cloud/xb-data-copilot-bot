"""确保历史大模型 / 业务数据源在库中可见（幂等修复名称与 provider）。"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.copilot import get_session_factory
from app.system.runtime_config import refresh_runtime_config
from config.settings import get_settings


async def main() -> None:
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                """
                UPDATE copilot_llm_model
                SET name = :name,
                    provider = :provider,
                    api_base = :api_base,
                    model_name = :model_name,
                    extra_json = :extra_json,
                    is_default = 1,
                    status = 1,
                    deleted = 0
                WHERE id = :id
                """
            ),
            {
                "id": 1,
                "name": "DeepSeek Chat",
                "provider": "deepseek",
                "api_base": "https://api.deepseek.com",
                "model_name": "deepseek-v4-flash",
                "extra_json": '{"thinking_enabled": true, "reasoning_effort": "high"}',
            },
        )
        await session.execute(
            text(
                """
                UPDATE copilot_llm_model
                SET name = :name,
                    provider = :provider,
                    api_base = :api_base,
                    model_name = :model_name,
                    extra_json = :extra_json,
                    is_default = 1,
                    status = 1,
                    deleted = 0
                WHERE id = :id
                """
            ),
            {
                "id": 2,
                "name": "Ollama Embedding",
                "provider": "ollama",
                "api_base": "http://127.0.0.1:11434/v1",
                "model_name": "qwen3-embedding:4b",
                "extra_json": '{"embedding_dims": 2560}',
            },
        )
        await session.execute(
            text(
                """
                UPDATE copilot_business_datasource
                SET name = :name,
                    db_type = 'mysql',
                    host = :host,
                    port = :port,
                    database_name = :database_name,
                    username = :username,
                    is_default = 1,
                    status = 1,
                    deleted = 0
                WHERE id = :id
                """
            ),
            {
                "id": 1,
                "name": "stugrow_sport",
                "host": "REDACTED_HOST",
                "port": 18306,
                "database_name": "stugrow_sport",
                "username": "REDACTED_USER",
            },
        )

        # 若记录不存在（例如全新库未跑 V016 种子），从 env 再种子一次
        llm_c = (
            await session.execute(
                text("SELECT COUNT(1) AS c FROM copilot_llm_model WHERE deleted = 0")
            )
        ).mappings().first()["c"]
        ds_c = (
            await session.execute(
                text(
                    "SELECT COUNT(1) AS c FROM copilot_business_datasource WHERE deleted = 0"
                )
            )
        ).mappings().first()["c"]

        if int(llm_c) == 0 or int(ds_c) == 0:
            from app.system.seed_from_env import seed_system_config_from_env

            await seed_system_config_from_env(session, settings)
        else:
            await session.commit()
            await refresh_runtime_config(session, settings)

        llm_rows = (
            await session.execute(
                text(
                    "SELECT id, name, role, provider, model_name, is_default "
                    "FROM copilot_llm_model WHERE deleted = 0"
                )
            )
        ).mappings().all()
        ds_rows = (
            await session.execute(
                text(
                    "SELECT id, name, host, port, database_name, is_default "
                    "FROM copilot_business_datasource WHERE deleted = 0"
                )
            )
        ).mappings().all()
        print("LLM:", [dict(r) for r in llm_rows])
        print("DS:", [dict(r) for r in ds_rows])


if __name__ == "__main__":
    asyncio.run(main())
