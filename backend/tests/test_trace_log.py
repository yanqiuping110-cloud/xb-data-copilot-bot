"""TraceLogCollector 与 trace_log 序列化测试。"""

from __future__ import annotations

import json

from app.observability.trace_log import (
    TraceLogCollector,
    build_final_summary,
    build_result_json,
    parse_result_snapshot,
    resolve_error_node,
    sanitize_detail,
)


def test_sanitize_detail_preserves_context_text_for_debug() -> None:
    prompt = "【允许查询的业务表】\n" + ("line\n" * 200)
    out = sanitize_detail({"context_text": prompt, "chars": len(prompt)})
    assert out is not None
    assert out["context_text"] == prompt
    assert "preview=" not in out["context_text"]


def test_sanitize_detail_truncates_oversized_context_text() -> None:
    from app.observability import trace_log

    huge = "x" * (trace_log._MAX_CONTEXT_TEXT_LEN + 1000)
    out = sanitize_detail({"context_text": huge})
    assert out is not None
    assert len(out["context_text"]) < len(huge)
    assert "已截断" in out["context_text"]


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


def test_sanitize_detail_preserves_sql_params() -> None:
    out = sanitize_detail(
        {
            "row_count": 5,
            "sql_preview": "SELECT 1 WHERE sch_id IN (:scope_school_0)",
            "sql_params": {"scope_school_0": 1140, "scope_school_1": 1220},
        }
    )
    assert out is not None
    assert out["sql_params"] == {"scope_school_0": 1140, "scope_school_1": 1220}


def test_build_final_summary() -> None:
    summary = build_final_summary(
        {
            "final_sql": "SELECT 1 WHERE sch_id IN (:scope_school_0)",
            "sql_params": {"scope_school_0": 1140},
            "answer": "共 1 行",
            "rows": [[1]],
            "degrade_level": 0,
            "retry_count": 1,
        }
    )
    assert summary["sql_preview"] == "SELECT 1 WHERE sch_id IN (:scope_school_0)"
    assert summary["sql_params"] == {"scope_school_0": 1140}
    assert summary["row_count"] == 1
    assert summary["retry_count"] == 1
    assert summary["answer_preview"] == "共 1 行"


def test_build_result_json_and_parse_snapshot() -> None:
    raw = build_result_json(
        answer="共 1 行",
        columns=["cnt"],
        rows=[[3]],
        error_message=None,
    )
    parsed = parse_result_snapshot(raw)
    assert parsed["answer"] == "共 1 行"
    assert parsed["columns"] == ["cnt"]
    assert parsed["rows"] == [[3]]

    trace = json.dumps(
        {
            "final": {"answer_preview": "预览回答", "rows_sample": [[1]]},
            "error_message": "表不在白名单",
        },
        ensure_ascii=False,
    )
    fallback = parse_result_snapshot(None, trace_log=trace)
    assert fallback["answer"] == "预览回答"
    assert fallback["rows"] == [[1]]
    assert fallback["error_message"] == "表不在白名单"


def test_non_stream_omits_first_token_in_json() -> None:
    collector = TraceLogCollector("trace-3", stream=False)
    collector.mark_first_token(99)
    payload = json.loads(
        collector.to_json(status="success", latency_ms_total=100)
    )
    assert "latency_ms_first_token" not in payload
