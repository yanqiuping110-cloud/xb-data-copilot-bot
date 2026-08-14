"""空表时从当前 env 种子 LLM / 业务数据源（幂等；不含任何硬编码主机或密钥）。"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.copilot import get_session_factory
from app.system.runtime_config import refresh_runtime_config
from app.system.seed_from_env import seed_system_config_from_env
from config.settings import get_settings


async def main() -> None:
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        await seed_system_config_from_env(session, settings)
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
                    "SELECT id, name, db_type, is_default "
                    "FROM copilot_business_datasource WHERE deleted = 0"
                )
            )
        ).mappings().all()
        print("LLM:", [dict(r) for r in llm_rows])
        print("DS:", [dict(r) for r in ds_rows])


if __name__ == "__main__":
    asyncio.run(main())
