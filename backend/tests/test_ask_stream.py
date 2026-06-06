"""问数 SSE 流式事件单测。"""

import json

from app.agent.streaming import (
    NODE_LABELS,
    done_event,
    error_event,
    format_sse,
    progress_event,
)
from app.ask.service import wants_stream
from app.schemas.ask import AskOptions, AskRequest, AskResponse


def test_wants_stream():
    assert not wants_stream(AskRequest(question="q"))
    assert not wants_stream(AskRequest(question="q", options=AskOptions(stream=False)))
    assert wants_stream(AskRequest(question="q", options=AskOptions(stream=True)))


def test_format_sse():
    frame = format_sse("progress", {"node": "recall_columns", "label": "召回相关字段"})
    assert frame.startswith("event: progress\n")
    assert "data:" in frame
    assert frame.endswith("\n\n")


def test_progress_event_uses_chinese_label():
    frame = progress_event("generate_sql")
    assert "生成 SQL" in frame
    assert "generate_sql" in frame


def test_done_event_camel_case():
    resp = AskResponse(trace_id="t1", status="success", answer="共 3 行")
    frame = done_event(resp)
    assert "event: done" in frame
    data_line = [ln for ln in frame.split("\n") if ln.startswith("data:")][0]
    payload = json.loads(data_line[5:].strip())
    assert payload["traceId"] == "t1"
    assert payload["answer"] == "共 3 行"


def test_error_event():
    frame = error_event("POLICY_ERROR", "未选学校")
    assert "POLICY_ERROR" in frame


def test_all_graph_nodes_have_labels():
    expected = {
        "normalize_question",
        "extract_keywords",
        "do_recall_columns",
        "do_recall_metrics",
        "do_recall_field_values",
        "merge_retrieved_info",
        "filter_tables",
        "filter_metrics",
        "build_llm_context",
        "match_curated",
        "generate_sql",
        "validate_sql",
        "correct_sql",
        "apply_policy",
        "execute_sql",
        "format_answer",
    }
    assert expected == set(NODE_LABELS.keys())
