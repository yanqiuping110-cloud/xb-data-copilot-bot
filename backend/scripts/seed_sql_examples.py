"""
写入 L1 样例 SQL 与指标定义（copilot_sql_example / copilot_metric_definition）。

用法（在 backend/ 目录）:
  $env:APP_ENV = "development"
  # 需先执行 scripts/sql/copilot/V003__sql_example_meta_json.sql
  python scripts/seed_sql_examples.py
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

_QZS = "sport_activity_qzs_record"

_METRICS = [
    {
        "metric_code": "qzs_month_participants",
        "metric_name": "本校本月活动参与人数",
        "description": "sport_activity_qzs_record 当月去重 people_id；学校账户按 sch_id 过滤。",
        "relevant_tables": _QZS,
        "alias_json": json.dumps(["参与人数", "本月参与", "这个月参与"], ensure_ascii=False),
    },
    {
        "metric_code": "qzs_weekly_trend",
        "metric_name": "最近7天每日参与人数",
        "description": "按 DATE(create_time) 分组统计去重 people_id。",
        "relevant_tables": _QZS,
        "alias_json": json.dumps(["7天趋势", "每日趋势", "最近7天"], ensure_ascii=False),
    },
    {
        "metric_code": "qzs_platform_yesterday",
        "metric_name": "昨日全平台打卡人次",
        "description": "昨日 DATE(create_time) 记录条数 COUNT(*)，仅超管/运营。",
        "relevant_tables": _QZS,
        "alias_json": json.dumps(["全平台", "平台汇总", "平台活动"], ensure_ascii=False),
    },
]

_EXAMPLES = [
    {
        "question_pattern": "昨日全平台活动参与人次",
        "sql_text": (
            f"SELECT COUNT(*) AS cnt FROM {_QZS} "
            f"WHERE DATE(create_time) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)"
        ),
        "role_scope": None,
        "degrade_priority": 10,
        "meta": {
            "matchAny": ["全平台", "平台汇总", "平台活动"],
            "adminOnly": True,
            "requiresSchoolFilter": False,
            "appendProjectClause": True,
            "answerTemplate": "昨日全平台活动打卡人次为 {cnt} 次。",
            "valueColumn": "cnt",
            "tables": [_QZS],
        },
    },
    {
        "question_pattern": "本校本月活动参与人数",
        "sql_text": (
            f"SELECT COUNT(DISTINCT people_id) AS cnt FROM {_QZS} "
            f"WHERE create_time >= DATE_FORMAT(CURDATE(), '%Y-%m-01')"
        ),
        "role_scope": None,
        "degrade_priority": 20,
        "meta": {
            "matchAllGroups": [["参与", "参与人数"], ["本月", "这个月"]],
            "answerTemplate": "本校本月活动参与人数为 {cnt} 人。",
            "valueColumn": "cnt",
            "tables": [_QZS],
        },
    },
    {
        "question_pattern": "本校活动参与人数（泛化）",
        "sql_text": (
            f"SELECT COUNT(DISTINCT people_id) AS cnt FROM {_QZS} "
            f"WHERE create_time >= DATE_FORMAT(CURDATE(), '%Y-%m-01')"
        ),
        "role_scope": None,
        "degrade_priority": 25,
        "meta": {
            "matchAll": ["参与人数"],
            "answerTemplate": "本校本月活动参与人数为 {cnt} 人。",
            "valueColumn": "cnt",
            "tables": [_QZS],
        },
    },
    {
        "question_pattern": "最近7天每日参与人数趋势",
        "sql_text": (
            f"SELECT DATE(create_time) AS stat_day, COUNT(DISTINCT people_id) AS cnt "
            f"FROM {_QZS} "
            f"WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
            f"GROUP BY DATE(create_time) ORDER BY stat_day"
        ),
        "role_scope": None,
        "degrade_priority": 20,
        "meta": {
            "matchAllGroups": [["7", "七", "最近"], ["趋势", "每日", "每天"]],
            "answerTemplate": "已返回最近 7 天每日参与人数，共 {row_count} 天数据。",
            "valueColumn": "cnt",
            "tables": [_QZS],
        },
    },
    {
        "question_pattern": "2025年跑步项目运动值",
        "sql_text": (
            "SELECT r.sport_value AS 运动值 "
            f"FROM {_QZS} r "
            "JOIN sport_project p ON r.project_id = p.id "
            "WHERE p.project_name = '跑步' AND YEAR(r.create_time) = 2025"
        ),
        "role_scope": None,
        "degrade_priority": 15,
        "meta": {
            "matchAllGroups": [["跑步"], ["运动值"]],
            "answerTemplate": "已返回 {row_count} 条运动值记录。",
            "valueColumn": "运动值",
            "tables": [_QZS, "sport_project"],
        },
    },
]


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.copilot_database_url, echo=False)
    async with engine.begin() as conn:
        for m in _METRICS:
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
        print(f"已写入/更新指标 {len(_METRICS)} 条")

        await conn.execute(
            text("UPDATE copilot_sql_example SET deleted = 1 WHERE question_pattern LIKE '本校%' OR question_pattern LIKE '昨日%' OR question_pattern LIKE '最近%'")
        )

        for ex in _EXAMPLES:
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
        print(f"已写入样例 SQL {len(_EXAMPLES)} 条（旧版同前缀样例已逻辑删除）")


if __name__ == "__main__":
    if not os.getenv("APP_ENV"):
        os.environ.setdefault("APP_ENV", "development")
    asyncio.run(main())
