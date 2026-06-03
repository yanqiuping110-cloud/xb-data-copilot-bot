"""检查业务库白名单表是否存在。"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.sql.whitelist import ALLOWED_TABLES
from config.settings import get_settings


async def main() -> None:
    s = get_settings()
    eng = create_async_engine(s.business_database_url)
    async with eng.connect() as conn:
        for table in sorted(ALLOWED_TABLES):
            r = await conn.execute(
                text(
                    "SELECT COUNT(1) FROM information_schema.tables "
                    "WHERE table_schema = :db AND table_name = :t"
                ),
                {"db": s.mysql_business_database, "t": table},
            )
            ok = bool(r.scalar())
            print(f"{table}: {'存在' if ok else '不存在'}")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
