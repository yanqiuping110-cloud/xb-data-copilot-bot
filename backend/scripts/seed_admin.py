"""
创建或重置默认超管（copilot_sys_user）。

用法（在 backend/ 目录）:
  $env:APP_ENV = "development"
  python scripts/seed_admin.py              # 尚无 ADMIN 时创建
  python scripts/seed_admin.py --reset-password   # 将 admin 密码重置为 SEED_ADMIN_PASSWORD

密码来自环境变量 SEED_ADMIN_PASSWORD，禁止写死在代码中。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main(*, reset_password: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.copilot_database_url, echo=False)
    password_hash = pwd_context.hash(settings.seed_admin_password)
    username = settings.seed_admin_username

    async with engine.begin() as conn:
        row = await conn.execute(
            text(
                """
                SELECT id FROM copilot_sys_user
                WHERE username = :u AND deleted = 0
                LIMIT 1
                """
            ),
            {"u": username},
        )
        existing = row.first()

        if existing:
            if not reset_password:
                admin_count = await conn.execute(
                    text("SELECT COUNT(*) AS c FROM copilot_sys_user WHERE role = 'ADMIN' AND deleted = 0")
                )
                if admin_count.scalar():
                    print(f"已存在用户 {username}，跳过种子（需重置请加 --reset-password）")
                    return
            await conn.execute(
                text(
                    """
                    UPDATE copilot_sys_user
                    SET password_hash = :p, updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"p": password_hash, "id": existing[0]},
            )
            print(f"已更新超管密码: {username}")
            return

        await conn.execute(
            text(
                """
                INSERT INTO copilot_sys_user (username, password_hash, display_name, role, status, created_by)
                VALUES (:u, :p, :d, 'ADMIN', 1, NULL)
                """
            ),
            {
                "u": username,
                "p": password_hash,
                "d": "系统管理员",
            },
        )
        print(f"已创建超管: {username}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建或重置默认超管")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="将 SEED_ADMIN_USERNAME 对应用户的密码重置为 SEED_ADMIN_PASSWORD",
    )
    args = parser.parse_args()
    if not os.getenv("APP_ENV"):
        os.environ.setdefault("APP_ENV", "development")
    asyncio.run(main(reset_password=args.reset_password))
