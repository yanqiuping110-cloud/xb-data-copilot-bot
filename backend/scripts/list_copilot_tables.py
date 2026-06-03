"""列出 study_demo 中 copilot_* 表。"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from config.settings import get_settings


async def main() -> None:
    s = get_settings()
    eng = create_async_engine(s.copilot_database_url)
    async with eng.connect() as conn:
        r = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :db AND table_name LIKE 'copilot_%' ORDER BY 1"
            ),
            {"db": s.mysql_copilot_database},
        )
        print([row[0] for row in r.fetchall()])
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
