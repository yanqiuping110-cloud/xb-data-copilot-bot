"""Diagnose double LEFT JOIN fan-out for activity compare query."""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import get_settings

ACTIVITY_FILTER = (
    "t1.status = 1 AND (t1.activity_name LIKE '%百廿雅礼系列活动%' "
    "OR t1.activity_name LIKE '%湖南省2026年度%校长喊你来运动%活动%')"
)


async def main() -> None:
    settings = get_settings()
    business = create_async_engine(settings.business_database_url, echo=False)

    joined_sql = f"""
        SELECT
            t1.activity_name,
            COUNT(DISTINCT t2.user_id) AS users,
            COALESCE(SUM(t2.sport_count), 0) AS punch_cnt,
            COALESCE(SUM(t3.order_total) / 100, 0) AS order_yuan
        FROM sport_activity_new AS t1
        LEFT JOIN sport_activity_qzs_time AS t2 ON t2.activity_id = t1.id
        LEFT JOIN sport_order AS t3
            ON t3.use_type_id = t1.id AND t3.pay_status = 1 AND t3.is_delete = 0
        WHERE {ACTIVITY_FILTER}
        GROUP BY t1.activity_name
    """

    cte_sql = f"""
        SELECT
            t1.activity_name,
            (
                SELECT COUNT(DISTINCT t2.user_id)
                FROM sport_activity_qzs_time AS t2
                WHERE t2.activity_id = t1.id
            ) AS users,
            (
                SELECT COALESCE(SUM(t2.sport_count), 0)
                FROM sport_activity_qzs_time AS t2
                WHERE t2.activity_id = t1.id
            ) AS punch_cnt,
            (
                SELECT COALESCE(SUM(t3.order_total) / 100, 0)
                FROM sport_order AS t3
                WHERE t3.use_type_id = t1.id
                  AND t3.pay_status = 1
                  AND t3.is_delete = 0
            ) AS order_yuan
        FROM sport_activity_new AS t1
        WHERE {ACTIVITY_FILTER}
    """

    counts_sql = f"""
        SELECT
            t1.activity_name,
            (
                SELECT COUNT(*)
                FROM sport_activity_qzs_time AS t2
                WHERE t2.activity_id = t1.id
            ) AS punch_rows,
            (
                SELECT COUNT(*)
                FROM sport_order AS t3
                WHERE t3.use_type_id = t1.id
                  AND t3.pay_status = 1
                  AND t3.is_delete = 0
            ) AS order_rows
        FROM sport_activity_new AS t1
        WHERE {ACTIVITY_FILTER}
    """

    async with business.connect() as conn:
        print("=== JOINED (double LEFT JOIN) ===")
        for row in (await conn.execute(text(joined_sql))).fetchall():
            print(row[1], row[2], row[3])

        print("=== CORRECT (separate subquery aggregate) ===")
        for row in (await conn.execute(text(cte_sql))).fetchall():
            print(row[1], row[2], row[3])

        print("=== RAW ROW COUNTS (fan-out multiplier ~= punch_rows * order_rows) ===")
        for row in (await conn.execute(text(counts_sql))).fetchall():
            _name, punch_rows, order_rows = row
            print(punch_rows, order_rows, "product", punch_rows * order_rows)

    copilot = create_async_engine(settings.copilot_database_url, echo=False)
    rel_sql = """
        SELECT ft.table_name AS from_table, r.from_column,
               tt.table_name AS to_table, r.to_column, r.join_hint
        FROM copilot_table_relation AS r
        JOIN copilot_table_meta AS ft ON ft.id = r.from_table_id AND ft.deleted = 0
        JOIN copilot_table_meta AS tt ON tt.id = r.to_table_id AND tt.deleted = 0
        WHERE r.deleted = 0 AND r.status = 1
          AND (
              ft.table_name IN ('sport_activity_new', 'sport_order', 'sport_activity_qzs_time')
              OR tt.table_name IN ('sport_activity_new', 'sport_order', 'sport_activity_qzs_time')
          )
    """
    async with copilot.connect() as conn:
        print("=== META RELATIONS ===")
        for row in (await conn.execute(text(rel_sql))).fetchall():
            print(row[0], row[1], row[2], row[3])

    await business.dispose()
    await copilot.dispose()


if __name__ == "__main__":
    asyncio.run(main())
