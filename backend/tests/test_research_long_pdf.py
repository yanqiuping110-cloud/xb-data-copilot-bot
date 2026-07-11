"""长报告 PDF 页数验收（8 节 ≥15 页）。"""

from pathlib import Path

from app.research.export_pdf import export_report_pdf
from app.research.planner import build_research_plan
from app.research.synthesizer import synthesize_report_document


def _section_results_from_plan(plan: dict) -> list[dict]:
    out = []
    for s in plan["sections"]:
        idx = s["index"]
        out.append(
            {
                "section_index": idx,
                "title": s["title"],
                "intent": s.get("intent"),
                "status": "success",
                "answer": f"{s['title']}：本月数据表现稳定，环比变化在预期范围内。",
                "columns": ["维度", "数值", "环比"],
                "rows": [[f"项{i}", str(100 + i), f"{i}%"] for i in range(1, 6)],
                "sub_trace_id": f"trace-{idx}",
                "latency_ms": 500 + idx * 10,
            }
        )
    return out


def test_monthly_ops_long_pdf_at_least_15_pages(tmp_path: Path):
    plan = build_research_plan("本月长报告", template_code="monthly_ops_long", max_sections=12)
    assert len(plan["sections"]) >= 8
    doc = synthesize_report_document(
        report_id="rpt-long-test",
        plan=plan,
        section_results=_section_results_from_plan(plan),
        scope_summary="ADMIN",
    )
    assert doc["meta"]["pageEstimate"] >= 20
    out = tmp_path / "long_report.pdf"
    page_count, size = export_report_pdf(doc, out)
    assert out.is_file()
    assert size > 5000
    assert page_count >= 15
