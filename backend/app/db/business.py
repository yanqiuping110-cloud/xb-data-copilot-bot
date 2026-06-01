"""
智慧体育业务库：只读连接（问数执行 SQL 时使用）。

本模块当前仅用于 /ready 连通性探测；执行层在 db/business 扩展或独立 executor。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import get_settings

_engine = None


def get_business_engine():
    """懒加载业务库引擎（只读账号）。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.business_database_url,
            pool_pre_ping=True,
        )
    return _engine


async def check_business_connection() -> bool:
    """就绪探针：能否连上业务只读库。"""
    try:
        engine = get_business_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
