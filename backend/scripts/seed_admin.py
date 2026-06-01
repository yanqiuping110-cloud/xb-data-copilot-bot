"""
创建默认超管（copilot_sys_user 中尚无 ADMIN 时）。

用法（在 backend/ 目录）:
  $env:APP_ENV = "development"
  python scripts/seed_admin.py

密码来自环境变量 SEED_ADMIN_PASSWORD，禁止写死在代码中。
"""

from __future__ import annotations

import asyncio
import os
import sys

from pathlib import Path

# 将 backend/ 加入 sys.path，以便 import config / app
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.copilot_database_url, echo=True)
    async with engine.begin() as conn:
        row = await conn.execute(
            text("SELECT COUNT(*) AS c FROM copilot_sys_user WHERE role = 'ADMIN'")
        )
        count = row.scalar()
        if count and count > 0:
            print("已存在 ADMIN 用户，跳过种子")
            return

        password_hash = pwd_context.hash(settings.seed_admin_password)
        await conn.execute(
            text(
                """
                INSERT INTO copilot_sys_user (username, password_hash, display_name, role, status, created_by)
                VALUES (:u, :p, :d, 'ADMIN', 1, NULL)
                """
            ),
            {
                "u": settings.seed_admin_username,
                "p": password_hash,
                "d": "系统管理员",
            },
        )
        print(f"已创建超管: {settings.seed_admin_username}")


if __name__ == "__main__":
    if not os.getenv("APP_ENV"):
        os.environ.setdefault("APP_ENV", "development")
    asyncio.run(main())
