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


def test_verify_passes_daily_metric_vs_shorter_alias():
    """plan「每日参与人数」与列「参与人数」应视为匹配。"""
    plan = {"metrics": ["每日参与人数"]}
    result = verify_answer_heuristic(
        "最近7天每日趋势",
        ["日期", "参与人数"],
        [["2026-07-05", 1]],
        plan=plan,
    )
    assert result["passed"] is True
    assert result["reason"] == "ok"


def test_verify_passes_when_ratio_metric_split_across_columns():
    """plan「活动运动人数占比」可由「活动运动人数」+「占比」两列满足。"""
    plan = {
        "metrics": ["活动运动人数占比"],
        "steps": [{"id": 1, "metrics": ["活动运动人数占比"]}],
    }
    result = verify_answer_heuristic(
        "用图表展示 2026年每个月的活动运动人数 占比情况，用饼状图展示",
        ["月份", "活动运动人数", "占比"],
        [["2026-03", 1, 0.9804], ["2026-04", 6, 5.8824]],
        plan=plan,
    )
    assert result["passed"] is True
    assert result["reason"] == "ok"
