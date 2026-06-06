"""问数节点日志摘要单测。"""

from app.agent.log_utils import get_node_label, get_status_label, summarize_state_update


def test_summarize_truncates_context_text():
    summary = summarize_state_update({"context_text": "a" * 500})
    assert summary["context_text"].startswith("len=500")


def test_summarize_sql_preview():
    summary = summarize_state_update({"final_sql": "SELECT 1 FROM sport_activity_qzs_record"})
    assert "SELECT 1" in summary["final_sql"]


def test_node_label_for_graph_and_span_names():
    assert get_node_label("generate_sql") == "生成 SQL"
    assert get_node_label("recall_metrics") == "召回相关指标"
    assert get_node_label("do_recall_metrics") == "召回相关指标"


def test_status_label():
    assert get_status_label("success") == "成功"
    assert get_status_label("empty") == "无结果"
