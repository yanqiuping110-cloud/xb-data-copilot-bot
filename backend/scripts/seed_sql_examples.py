"""
写入 L1 样例 SQL 与指标定义（copilot_sql_example / copilot_metric_definition）。

用法（在 backend/ 目录）:
  $env:APP_ENV = "development"
  $env:SEED_PRIMARY_TABLE = "sport_activity_qzs_time"   # 须已在 copilot_table_meta 注册
  python scripts/seed_sql_examples.py

表名/列名以 SEED_PRIMARY_TABLE 与库内 meta 为准，不在脚本中写死业务枚举（如具体项目名）。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import get_settings

_PRIMARY = (os.getenv("SEED_PRIMARY_TABLE") or "").strip()


def _metrics(table: str) -> list[dict]:
    return [
        {
            "metric_code": "qzs_month_participants",
            "metric_name": "本校本月活动参与人数",
            "description": f"{table} 当月去重人员；学校账户按 sch_id 过滤。",
            "relevant_tables": table,
            "alias_json": json.dumps(["参与人数", "本月参与", "这个月参与"], ensure_ascii=False),
        },
        {
            "metric_code": "qzs_weekly_trend",
            "metric_name": "最近7天每日参与人数",
            "description": "按日分组统计去重人员（日期列以 meta 为准）。",
            "relevant_tables": table,
            "alias_json": json.dumps(["7天趋势", "每日趋势", "最近7天"], ensure_ascii=False),
        },
        {
            "metric_code": "qzs_platform_yesterday",
            "metric_name": "昨日全平台打卡人次",
            "description": "昨日记录条数 COUNT(*)，仅超管/运营。",
            "relevant_tables": table,
            "alias_json": json.dumps(["全平台", "平台汇总", "平台活动"], ensure_ascii=False),
        },
    ]


def _examples(table: str) -> list[dict]:
    # 列名（record_date / user_id 等）须与 copilot_column_meta 一致；此处为常见打卡表示例。
    return [
        {
            "question_pattern": "昨日全平台活动参与人次",
            "sql_text": (
                f"SELECT COUNT(*) AS cnt FROM {table} "
                f"WHERE DATE(record_date) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)"
            ),
            "role_scope": None,
            "degrade_priority": 10,
            "meta": {
                "matchAny": ["全平台", "平台汇总", "平台活动"],
                "adminOnly": True,
                "requiresSchoolFilter": False,
                "answerTemplate": "昨日全平台活动打卡人次为 {cnt} 次。",
                "valueColumn": "cnt",
                "tables": [table],
            },
        },
        {
            "question_pattern": "本校本月活动参与人数",
            "sql_text": (
                f"SELECT COUNT(DISTINCT user_id) AS cnt FROM {table} "
                f"WHERE record_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')"
            ),
            "role_scope": None,
            "degrade_priority": 20,
            "meta": {
                "matchAllGroups": [["参与", "参与人数"], ["本月", "这个月"]],
                "answerTemplate": "本校本月活动参与人数为 {cnt} 人。",
                "valueColumn": "cnt",
                "tables": [table],
            },
        },
        {
            "question_pattern": "最近7天每日参与人数趋势",
            "sql_text": (
                f"SELECT DATE(record_date) AS stat_day, COUNT(DISTINCT user_id) AS cnt "
                f"FROM {table} "
                f"WHERE record_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
                f"GROUP BY DATE(record_date) ORDER BY stat_day"
            ),
            "role_scope": None,
            "degrade_priority": 20,
            "meta": {
                "matchAllGroups": [["7", "七", "最近"], ["趋势", "每日", "每天"]],
                "answerTemplate": "已返回最近 7 天每日参与人数，共 {row_count} 天数据。",
                "valueColumn": "cnt",
                "tables": [table],
            },
        },
    ]


async def main() -> None:
    if not _PRIMARY:
        print("请设置环境变量 SEED_PRIMARY_TABLE（已在 copilot_table_meta 注册的表名）")
        sys.exit(1)

    settings = get_settings()
    engine = create_async_engine(settings.copilot_database_url, echo=False)
    metrics = _metrics(_PRIMARY)
    examples = _examples(_PRIMARY)

    async with engine.begin() as conn:
        for m in metrics:
            await conn.execute(
                text(
                    """
                    INSERT INTO copilot_metric_definition (
                        metric_code, metric_name, description, relevant_tables, alias_json, status, deleted
                    ) VALUES (
                        :metric_code, :metric_name, :description, :relevant_tables, :alias_json, 1, 0
                    )
                    ON DUPLICATE KEY UPDATE
                        metric_name = VALUES(metric_name),
                        description = VALUES(description),
                        relevant_tables = VALUES(relevant_tables),
                        alias_json = VALUES(alias_json),
                        status = 1,
                        deleted = 0
                    """
                ),
                m,
            )
        print(f"已写入/更新指标 {len(metrics)} 条（主表={_PRIMARY}）")

        for ex in examples:
            await conn.execute(
                text(
                    """
                    INSERT INTO copilot_sql_example (
                        question_pattern, sql_text, role_scope, degrade_priority, meta_json, deleted
                    ) VALUES (
                        :question_pattern, :sql_text, :role_scope, :degrade_priority, :meta_json, 0
                    )
                    """
                ),
                {
                    "question_pattern": ex["question_pattern"],
                    "sql_text": ex["sql_text"],
                    "role_scope": ex["role_scope"],
                    "degrade_priority": ex["degrade_priority"],
                    "meta_json": json.dumps(ex["meta"], ensure_ascii=False),
                },
            )
        print(f"已写入样例 SQL {len(examples)} 条（主表={_PRIMARY}）")


if __name__ == "__main__":
    if not os.getenv("APP_ENV"):
        os.environ.setdefault("APP_ENV", "development")
    asyncio.run(main())
