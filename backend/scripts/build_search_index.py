"""
从 copilot 元数据全量重建问数检索索引（默认 Zvec）。

用法（在 backend/ 目录）:
  $env:APP_ENV = "development"
  # 需已 seed_semantic_meta.py；Ollama embedding 可用
  python scripts/build_search_index.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.meta.index_service import MetaKnowledgeService
from config.settings import get_settings


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.copilot_database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        svc = MetaKnowledgeService(session, settings)
        try:
            if not await svc.ping_search_index():
                print(
                    f"警告：检索后端不可用（VECTOR_STORE={settings.vector_store}），"
                    "请检查 ZVEC_DATA_DIR 或 ELASTICSEARCH_URL"
                )
                return
            result = await svc.rebuild_all()
            print(
                f"索引重建完成：表 {result.tables} 条，字段 {result.columns} 条，"
                f"指标 {result.metrics} 条，取值 {result.field_values} 条，"
                f"向量维度 {result.embedding_dims}"
            )
        finally:
            await svc.close()


if __name__ == "__main__":
    if not os.getenv("APP_ENV"):
        os.environ.setdefault("APP_ENV", "development")
    asyncio.run(main())
