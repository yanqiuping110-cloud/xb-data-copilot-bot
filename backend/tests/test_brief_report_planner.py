"""Brief Report LLM 降级单测。"""

from app.brief_report.planner_llm import _fallback_plan


def test_fallback_plan_without_llm():
    turns = [
        {
            "question": "本月跳绳参与人数",
            "answer": "共 1200 人参与，较上月增长 8%。",
        }
    ]
    plan = _fallback_plan(turns, "教育局汇报")
    assert plan["cover"]["title"]
    assert len(plan["toc"]) == 1
    assert plan["toc"][0]["summary"]
    assert plan["ending"]["headline"] == "感谢聆听"
