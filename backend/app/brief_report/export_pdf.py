"""BriefReportDocument → PDF（Canvas 精美版优先，WeasyPrint 备选）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.brief_report.pdf_canvas import export_brief_report_pdf_canvas
from app.brief_report.render_html import render_brief_report_html
from config.settings import Settings, get_settings


def export_brief_report_pdf(
    doc: dict[str, Any],
    output_path: Path,
    *,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """写入 PDF，返回 (page_count, file_size_bytes)。"""
    cfg = settings or get_settings()
    engine = (cfg.brief_report_pdf_engine or "auto").lower()

    if engine == "html":
        return _export_via_html(doc, output_path)

    if engine in ("auto", "canvas", "reportlab"):
        try:
            if engine == "auto":
                return _try_weasyprint_then_canvas(doc, output_path)
            return export_brief_report_pdf_canvas(doc, output_path)
        except Exception:
            if engine in ("canvas", "reportlab"):
                raise

    return export_brief_report_pdf_canvas(doc, output_path)


def _try_weasyprint_then_canvas(doc: dict[str, Any], output_path: Path) -> tuple[int, int]:
    try:
        return _export_via_html(doc, output_path)
    except Exception:
        return export_brief_report_pdf_canvas(doc, output_path)


def _export_via_html(doc: dict[str, Any], output_path: Path) -> tuple[int, int]:
    from weasyprint import HTML

    html = render_brief_report_html(doc)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(output_path.parent)).write_pdf(str(output_path))
    data = output_path.read_bytes()
    page_count = _estimate_page_count(doc)
    return page_count, len(data)


def _estimate_page_count(doc: dict[str, Any]) -> int:
    chapters = len(doc.get("chapters") or [])
    return max(3, 2 + chapters)
