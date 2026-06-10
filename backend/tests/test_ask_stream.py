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
    from app.agent.graph import build_ask_graph

    graph = build_ask_graph(recall_columns_enabled=False)
    skip = {"__start__", "__end__"}
    for node in graph.nodes:
        if node in skip:
            continue
        assert node in NODE_LABELS, f"missing label for graph node: {node}"
    assert "do_recall_columns" not in graph.nodes
