"""progress 载荷脱敏 summary 单测。"""

from app.agent.progress_payload import build_progress_summary, node_to_phase


def test_summary_keywords():
    s = build_progress_summary("extract_keywords", {"keywords": ["活动", "月份"]})
    assert s == "关键词：活动、月份"


def test_summary_recall_count_no_table_names():
    s = build_progress_summary("do_recall_tables", {"count": 3})
    assert s == "命中 3 张候选表"
    assert "sport_" not in (s or "")


def test_node_to_phase():
    assert node_to_phase("execute_sql")[0] == "execute"
    assert node_to_phase("format_answer")[0] == "answer"
