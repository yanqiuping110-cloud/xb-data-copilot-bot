"""Plan 分步 SQL 工具与 LLM plan 规范化单测。"""

from app.agent.plan_compare import (
    enrich_sql_steps_from_reference_sql,
    extract_activity_ids_from_sql,
    get_sql_execution_steps,
    plan_requires_multi_sql,
)
from app.agent.plan_llm import _normalize_plan


def test_normalize_plan_multi_sql_steps():
    raw = {
        "complexity": "high",
        "intent": "entity_compare",
        "multi_sql": True,
        "metrics": ["打卡人数", "跳绳运动个数"],
        "assembly_mode": "join_by_date",
        "join_key": "日期",
        "steps": [
            {
                "id": 1,
                "goal": "活动A",
                "sql_step": True,
                "entity_label": "A",
                "filter_hint": {"activity_id": 5780},
            },
            {
                "id": 2,
                "goal": "活动B",
                "sql_step": True,
                "entity_label": "B",
                "filter_hint": {"activity_id": 5680},
            },
        ],
    }
    plan = _normalize_plan(raw)
    assert plan["multi_sql"] is True
    assert plan["metrics"] == ["打卡人数", "跳绳运动个数"]
    assert len(get_sql_execution_steps(plan)) == 2
    assert plan_requires_multi_sql(plan)


def test_plan_requires_multi_sql_from_flag_only():
    plan = {"multi_sql": True, "steps": [{"id": 1, "goal": "x", "sql_step": False}]}
    assert plan_requires_multi_sql(plan)


def test_extract_ids_from_l1_sql():
    sql = (
        "SELECT ... FROM sport_activity_new AS a1 "
        "WHERE a1.id IN (5780, 5680) GROUP BY ..."
    )
    ids = extract_activity_ids_from_sql(sql)
    assert 5780 in ids and 5680 in ids
    plan = enrich_sql_steps_from_reference_sql(
        {
            "multi_sql": True,
            "steps": [
                {"id": 1, "sql_step": True, "filter_hint": {}},
                {"id": 2, "sql_step": True, "filter_hint": {}},
            ],
        },
        sql,
    )
    assert plan["steps"][0]["filter_hint"]["activity_id"] == 5780
    assert plan["steps"][1]["filter_hint"]["activity_id"] == 5680
