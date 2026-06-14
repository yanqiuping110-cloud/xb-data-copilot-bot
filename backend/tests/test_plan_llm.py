"""plan_llm _normalize_plan 单测。"""

from app.agent.plan_llm import _normalize_plan


def test_normalize_low_single_sql_not_multi():
    plan = _normalize_plan(
        {
            "complexity": "low",
            "multi_sql": False,
            "steps": [{"id": 1, "goal": "统计人数", "needs_tool": ["describe_table"]}],
        }
    )
    assert plan["multi_sql"] is False
    assert plan["complexity"] == "low"
