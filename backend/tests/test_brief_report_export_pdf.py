"""Brief Report PDF 导出单测。"""

from pathlib import Path

from app.brief_report.builder import build_brief_report_document
from app.brief_report.export_pdf import export_brief_report_pdf


def test_export_brief_report_pdf_writes_file(tmp_path: Path):
    turns = [
        {
            "trace_id": "trace-pdf-1",
            "question": "各校参与人数对比",
            "answer": "A校参与人数最多，B校次之。",
            "columns": ["学校", "人数"],
            "rows": [["A校", 200], ["B校", 150]],
            "chart_spec": None,
        }
    ]
    doc = build_brief_report_document(
        session_id="sess-pdf",
        user_prompt="面向区教育局领导的数据分析汇报材料",
        turns=turns,
        work_dir=tmp_path / "work",
    )
    out = tmp_path / "report.pdf"
    page_count, size = export_brief_report_pdf(doc, out)
    assert out.is_file()
    assert size > 500
    assert page_count >= 3
