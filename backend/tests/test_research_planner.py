"""Research planner 单测。"""

from app.research.planner import build_research_plan


def test_monthly_ops_plan_has_four_sections():
    plan = build_research_plan("本月运营分析", template_code="monthly_ops")
    assert len(plan["sections"]) == 4
    assert plan["sections"][0]["index"] == 1
    assert plan["sections"][0]["intent"] == "trend"


def test_monthly_ops_long_respects_max_sections():
    plan = build_research_plan("长报告", template_code="monthly_ops_long", max_sections=5)
    assert len(plan["sections"]) == 5


def test_custom_template_splits_request():
    text = "本月 KPI 汇总；各区域对比；异常指标分析"
    plan = build_research_plan(text, template_code="custom", max_sections=12)
    assert len(plan["sections"]) >= 2
    assert plan["templateCode"] == "custom"


def test_title_truncation():
    long_text = "A" * 50
    plan = build_research_plan(long_text)
    assert plan["title"].endswith("…")
    assert len(plan["title"]) <= 41
