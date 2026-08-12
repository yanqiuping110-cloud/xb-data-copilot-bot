"""
按 .env 中 MYSQL_COPILOT_DATABASE，人工执行 scripts/sql/copilot/ 版本 DDL。

⚠️ 问数库表结构禁止在应用运行时变更；本脚本仅作 DBA/开发人工初始化辅助。

用法（backend/ 目录）:
  $env:APP_ENV = "development"
  python scripts/apply_ddl_to_env_db.py --manual-confirm
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import get_settings

SQL_DIR = ROOT / "scripts" / "sql" / "copilot"


def _statements_from_file(path: Path, database: str) -> list[str]:
    ddl_text = path.read_text(encoding="utf-8")
    ddl_text = ddl_text.replace("USE copilot;", f"USE {database};")
    statements: list[str] = []
    buf: list[str] = []
    for line in ddl_text.splitlines():
        stripped = line.strip()
        if "FOREIGN KEY" in stripped or (
            stripped.startswith("CONSTRAINT ") and "REFERENCES" in stripped
        ):
            continue
        s = stripped
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        if s.endswith(";"):
            stmt = "\n".join(buf)
            stmt = re.sub(r",\s*\)", ")", stmt)
            statements.append(stmt)
            buf = []
    return statements


def _version_files() -> list[Path]:
    files = sorted(SQL_DIR.glob("V*.sql"))
    if not files:
        legacy = ROOT / "scripts" / "ddl_copilot.sql"
        if legacy.is_file():
            return [legacy]
    return files


async def main(manual_confirm: bool) -> None:
    if not manual_confirm:
        print("错误：问数库 DDL 只能人工确认后执行。")
        print("用法: python scripts/apply_ddl_to_env_db.py --manual-confirm")
        print("策略: docs/90-DATABASE_CHANGE_POLICY.md")
        sys.exit(1)

    settings = get_settings()
    db = settings.mysql_copilot_database
    version_files = _version_files()
    if not version_files:
        print(f"未找到 SQL 版本文件: {SQL_DIR}/V*.sql")
        sys.exit(1)

    engine = create_async_engine(settings.copilot_database_url, echo=False)
    total = 0
    async with engine.begin() as conn:
        for vf in version_files:
            stmts = _statements_from_file(vf, db)
            for stmt in stmts:
                await conn.execute(text(stmt))
                total += 1
            print(f"已执行: {vf.name} ({len(stmts)} 条语句)")
    await engine.dispose()
    print(f"完成：database={db}，共 {total} 条 DDL（CREATE IF NOT EXISTS）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="人工执行问数库版本 DDL")
    parser.add_argument(
        "--manual-confirm",
        action="store_true",
        help="确认已阅读 DATABASE_CHANGE_POLICY，人工执行 DDL",
    )
    args = parser.parse_args()
    asyncio.run(main(args.manual_confirm))
