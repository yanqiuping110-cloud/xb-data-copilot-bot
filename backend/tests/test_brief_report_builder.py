"""Brief Report 文档组装单测。"""

from pathlib import Path

from app.brief_report.builder import build_brief_report_document


def test_build_brief_report_document_basic(tmp_path: Path):
    turns = [
        {
            "trace_id": "trace-1",
            "question": "2026年每月活动运动次数趋势如何？",
            "answer": "整体呈上升趋势，3月达到峰值。",
            "columns": ["月份", "次数"],
            "rows": [["1月", 100], ["2月", 120]],
            "chart_spec": None,
            "final_sql": "SELECT 1",
        }
    ]
    doc = build_brief_report_document(
        session_id="sess-1",
        user_prompt="面向区教育局的智慧体育建设汇报",
        turns=turns,
        options={"org": "测试教育局"},
        work_dir=tmp_path,
    )
    assert doc["meta"]["sessionId"] == "sess-1"
    assert doc["cover"]["org"] == "测试教育局"
    assert len(doc["chapters"]) == 1
    assert doc["chapters"][0]["question"].startswith("2026")
    assert len(doc["toc"]) == 1
    assert doc["toc"][0]["code"] == "01"
