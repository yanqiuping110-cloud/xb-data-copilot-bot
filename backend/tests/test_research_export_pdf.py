"""PDF 导出离线单测。"""

from pathlib import Path

from app.research.export_pdf import export_report_pdf
from app.research.synthesizer import synthesize_report_document


def test_export_report_pdf_writes_file(tmp_path: Path):
    doc = synthesize_report_document(
        report_id="rpt-pdf-test",
        plan={"title": "PDF 测试报告", "sections": []},
        section_results=[
            {
                "section_index": 1,
                "title": "概览",
                "intent": "trend",
                "status": "success",
                "answer": "测试数据正常",
                "columns": ["A", "B"],
                "rows": [["1", "2"]],
                "sub_trace_id": "t1",
                "latency_ms": 100,
            }
        ],
        scope_summary="test scope",
    )
    out = tmp_path / "report.pdf"
    page_count, size = export_report_pdf(doc, out)
    assert out.is_file()
    assert size > 1000
    assert page_count >= 3
