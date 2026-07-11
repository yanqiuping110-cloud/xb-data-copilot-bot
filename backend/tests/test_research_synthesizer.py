"""ReportDocument 合成单测。"""

from app.research.synthesizer import synthesize_report_document


def _sample_sections():
    return [
        {
            "section_index": 1,
            "title": "总体 KPI",
            "intent": "trend",
            "status": "success",
            "answer": "本月销售额增长 12%",
            "columns": ["指标", "数值"],
            "rows": [["销售额", "1000"]],
            "sub_trace_id": "trace-a",
            "latency_ms": 1200,
        },
        {
            "section_index": 2,
            "title": "异常项",
            "intent": "anomaly",
            "status": "fail",
            "answer": None,
            "error_code": "NO_DATA",
            "sub_trace_id": "trace-b",
            "latency_ms": 800,
        },
    ]


def test_synthesize_report_document_structure():
    doc = synthesize_report_document(
        report_id="rpt-test001",
        plan={"title": "测试报告", "sections": []},
        section_results=_sample_sections(),
        scope_summary="ADMIN",
    )
    assert doc["meta"]["reportId"] == "rpt-test001"
    assert len(doc["chapters"]) == 2
    assert doc["chapters"][0]["status"] == "success"
    assert doc["chapters"][1]["status"] == "fail"
    assert doc["executiveSummary"]["paragraphs"]
    assert doc["recommendations"]
    assert doc["appendix"]["traces"]


def test_synthesize_includes_table_when_rows_present():
    doc = synthesize_report_document(
        report_id="rpt-test002",
        plan={"title": "T"},
        section_results=_sample_sections(),
        scope_summary="ADMIN",
    )
    tables = doc["chapters"][0]["tables"]
    assert len(tables) == 1
    assert tables[0]["columns"] == ["指标", "数值"]
