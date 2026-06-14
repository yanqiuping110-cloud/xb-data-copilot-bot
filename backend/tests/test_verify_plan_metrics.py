"""verify_answer 与 plan metrics 校验单测。"""

from app.agent.verify_nodes import verify_answer_heuristic


def test_verify_fails_when_plan_metrics_missing_in_columns():
    plan = {
        "metrics": ["打卡人数", "跳绳运动个数", "跑步运动个数"],
        "steps": [
            {
                "id": 1,
                "metrics": ["打卡人数", "跳绳运动个数", "跑步运动个数"],
            }
        ],
    }
    result = verify_answer_heuristic(
        "三个活动打卡跳绳跑步每日对比",
        ["日期", "打卡人数", "运动个数"],
        [["2026-05-20", 1, 100]],
        plan=plan,
    )
    assert result["passed"] is False
    assert result["reason"] == "missing_plan_metrics"
    assert "跳绳" in "".join(result["missing_terms"])


def test_verify_passes_when_plan_metrics_in_columns():
    plan = {"metrics": ["打卡人数", "跳绳运动个数", "跑步运动个数"]}
    result = verify_answer_heuristic(
        "对比",
        ["日期", "打卡人数", "跳绳运动个数", "跑步运动个数"],
        [["2026-05-20", 1, 10, 20]],
        plan=plan,
    )
    assert result["passed"] is True
