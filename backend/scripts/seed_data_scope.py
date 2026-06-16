"""
DataScope 种子：从 copilot_sys_user_school 迁移 school 维度 grant（第 13 周）。

用法（backend/ 目录）:
  $env:APP_ENV = "development"
  python scripts/seed_data_scope.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.copilot import async_session_factory  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        # 为已注册表绑定 school 维度（列名取自 table_meta.sch_id_column）
        await session.execute(
            text(
                """
                INSERT INTO copilot_table_scope_binding (table_id, dimension_code, column_name)
                SELECT tm.id, 'school', tm.sch_id_column
                FROM copilot_table_meta tm
                WHERE tm.deleted = 0 AND tm.status = 1
                  AND NOT EXISTS (
                    SELECT 1 FROM copilot_table_scope_binding b
                    WHERE b.table_id = tm.id AND b.dimension_code = 'school' AND b.deleted = 0
                  )
                """
            )
        )

        # 学校用户：sch_id → data_grant + 全表白名单 grant
        users = await session.execute(
            text(
                """
                SELECT u.id AS user_id, GROUP_CONCAT(us.sch_id) AS sch_ids
                FROM copilot_sys_user u
                JOIN copilot_sys_user_school us ON us.user_id = u.id AND us.deleted = 0
                WHERE u.deleted = 0 AND u.role = 'SCHOOL'
                GROUP BY u.id
                """
            )
        )
        tables = await session.execute(
            text(
                """
                SELECT table_name FROM copilot_table_meta
                WHERE deleted = 0 AND status = 1
                """
            )
        )
        table_names = [r["table_name"] for r in tables.mappings()]

        for row in users.mappings():
            uid = int(row["user_id"])
            sch_ids = [int(x) for x in (row["sch_ids"] or "").split(",") if x]
            if not sch_ids:
                continue
            await session.execute(
                text(
                    """
                    INSERT INTO copilot_user_data_grant (
                        user_id, dimension_code, operator, values_json, created_by
                    ) VALUES (:uid, 'school', 'in', :vals, NULL)
                    ON DUPLICATE KEY UPDATE
                        values_json = VALUES(values_json),
                        deleted = 0,
                        updated_at = NOW()
                    """
                ),
                {"uid": uid, "vals": json.dumps(sch_ids)},
            )
            for tname in table_names:
                await session.execute(
                    text(
                        """
                        INSERT INTO copilot_user_table_grant (user_id, table_name, effect)
                        VALUES (:uid, :tname, 'allow')
                        ON DUPLICATE KEY UPDATE deleted = 0, updated_at = NOW()
                        """
                    ),
                    {"uid": uid, "tname": tname},
                )

        await session.commit()
        print("DataScope 种子完成：table_scope_binding + SCHOOL 用户 grant")


if __name__ == "__main__":
    asyncio.run(main())
