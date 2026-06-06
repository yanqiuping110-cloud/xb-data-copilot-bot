"""TraceLogCollector 与 trace_log 序列化测试。"""

from __future__ import annotations

import json

from app.observability.trace_log import (
    TraceLogCollector,
    build_final_summary,
    resolve_error_node,
    sanitize_detail,
)


def test_sanitize_detail_truncates_sql() -> None:
    long_sql = "SELECT " + "x" * 5000
    out = sanitize_detail({"sql_preview": long_sql})
    assert out is not None
    assert len(out["sql_preview"]) < 5000
    assert out["sql_preview"].endswith("...")


def test_collector_append_node_and_to_json() -> None:
    collector = TraceLogCollector("trace-1", stream=True)
    collector.mark_first_token(120)
    collector.append_node("normalize_question", "清洗问句", "success", 2, {"length": 10})
    collector.append_node(
        "execute_sql",
        "执行查询",
        "fail",
        45,
        {"error_code": "SQL_EXEC_ERROR", "error_message": "Unknown column"},
    )

    text = collector.to_json(
        status="fail",
        latency_ms_total=500,
        error_code="SQL_EXEC_ERROR",
        error_message="SQL 执行失败",
        error_node="execute_sql",
        final={"row_count": 0},
    )
    payload = json.loads(text)
    assert payload["version"] == 1
    assert payload["trace_id"] == "trace-1"
    assert payload["stream"] is True
    assert payload["latency_ms_first_token"] == 120
    assert len(payload["nodes"]) == 2
    assert payload["nodes"][1]["node"] == "execute_sql"
    assert payload["error_node"] == "execute_sql"


def test_collector_fatal_and_resolve_error_node() -> None:
    collector = TraceLogCollector("trace-2", stream=False)
    collector.append_fatal(error_code="STREAM_ERROR", error_message="boom")
    assert resolve_error_node(collector, error_code="STREAM_ERROR") == "fatal"

    collector.append_node("generate_sql", "生成 SQL", "fail", 100, {"error_code": "LLM_NO_SQL"})
    assert resolve_error_node(collector, error_code="LLM_NO_SQL") == "generate_sql"


def test_build_final_summary() -> None:
    summary = build_final_summary(
        {
            "final_sql": "SELECT 1",
            "answer": "共 1 行",
            "rows": [[1]],
            "degrade_level": 0,
            "retry_count": 1,
        }
    )
    assert summary["row_count"] == 1
    assert summary["sql_preview"] == "SELECT 1"
    assert summary["answer_preview"] == "共 1 行"


def test_non_stream_omits_first_token_in_json() -> None:
    collector = TraceLogCollector("trace-3", stream=False)
    collector.mark_first_token(99)
    payload = json.loads(
        collector.to_json(status="success", latency_ms_total=100)
    )
    assert "latency_ms_first_token" not in payload
