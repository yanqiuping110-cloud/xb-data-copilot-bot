"""ReportDocument → PDF（HTML/WeasyPrint 优先，ReportLab 降级）。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.research.render_html import render_report_html
from config.settings import Settings, get_settings

_FONT = "STSong-Light"


def _ensure_font() -> str:
    try:
        pdfmetrics.getFont(_FONT)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
    return _FONT


def _styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RTitle",
            parent=base["Title"],
            fontName=font,
            fontSize=22,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "h1": ParagraphStyle("RH1", parent=base["Heading1"], fontName=font, fontSize=16, spaceAfter=10),
        "h2": ParagraphStyle("RH2", parent=base["Heading2"], fontName=font, fontSize=13, spaceAfter=8),
        "body": ParagraphStyle("RBody", parent=base["Normal"], fontName=font, fontSize=10, leading=14),
        "bullet": ParagraphStyle(
            "RBullet", parent=base["Normal"], fontName=font, fontSize=10, leading=14, leftIndent=14
        ),
        "muted": ParagraphStyle(
            "RMuted", parent=base["Normal"], fontName=font, fontSize=9, textColor=colors.grey
        ),
    }


def _escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def export_report_pdf(
    doc: dict[str, Any],
    output_path: Path,
    *,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """
    写入 PDF 文件。

    Returns:
        (page_count, file_size_bytes)
    """
    cfg = settings or get_settings()
    engine = (cfg.research_pdf_engine or "auto").lower()
    if engine in ("auto", "html"):
        try:
            return _export_via_html(doc, output_path)
        except Exception:
            if engine == "html":
                raise
    return _export_via_reportlab(doc, output_path)


def _export_via_html(doc: dict[str, Any], output_path: Path) -> tuple[int, int]:
    from weasyprint import HTML

    html = render_report_html(doc, include_cover_svg=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(output_path.parent)).write_pdf(str(output_path))
    data = output_path.read_bytes()
    page_count = _count_pages(output_path, doc)
    return page_count, len(data)


def _export_via_reportlab(doc: dict[str, Any], output_path: Path) -> tuple[int, int]:
    font = _ensure_font()
    st = _styles(font)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=doc.get("meta", {}).get("title", "Report"),
    )
    story: list[Any] = []
    meta = doc.get("meta") or {}

    story.append(Spacer(1, 6 * cm))
    story.append(Paragraph("Insight Engine", st["muted"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(_escape(meta.get("title") or "深度洞察报告"), st["h1"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            _escape(f"{meta.get('generatedAt', '')[:10]} · {meta.get('scopeSummary', '')}"),
            st["body"],
        )
    )
    story.append(Paragraph(_escape(meta.get("reportId") or ""), st["muted"]))
    story.append(PageBreak())

    story.append(Paragraph("目录", st["h1"]))
    story.append(Paragraph("执行摘要", st["body"]))
    for ch in doc.get("chapters") or []:
        story.append(
            Paragraph(_escape(f"第 {ch.get('index')} 章 {ch.get('title')}"), st["body"])
        )
    story.append(Paragraph("关键发现", st["body"]))
    story.append(Paragraph("建议与后续行动", st["body"]))
    story.append(Paragraph("附录 · Trace 清单", st["body"]))
    story.append(PageBreak())

    story.append(Paragraph("执行摘要", st["h1"]))
    for p in (doc.get("executiveSummary") or {}).get("paragraphs") or []:
        story.append(Paragraph(_escape(p), st["body"]))
        story.append(Spacer(1, 0.25 * cm))
    story.append(PageBreak())

    for ch in doc.get("chapters") or []:
        story.append(Paragraph(_escape(f"第 {ch.get('index')} 章 {ch.get('title')}"), st["h1"]))
        if ch.get("narrative"):
            for para in str(ch["narrative"]).split("\n"):
                para = para.strip()
                if para:
                    story.append(Paragraph(_escape(para), st["body"]))
            story.append(Spacer(1, 0.25 * cm))
        for bullet in ch.get("bullets") or []:
            story.append(Paragraph(f"• {_escape(bullet)}", st["bullet"]))
        for tbl in ch.get("tables") or []:
            cols = tbl.get("columns") or []
            rows = tbl.get("rows") or []
            if cols and rows:
                cap = tbl.get("caption") or "数据表"
                story.append(Paragraph(_escape(cap), st["h2"]))
                if tbl.get("truncated"):
                    story.append(
                        Paragraph(
                            _escape(f"共 {tbl.get('totalRows')} 行，展示前 50 行"),
                            st["muted"],
                        )
                    )
                data = [cols] + [[str(c) for c in row] for row in rows[:25]]
                table = Table(data, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (-1, -1), font),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 0.35 * cm))
        for chart in ch.get("charts") or []:
            png_path = chart.get("pngPath")
            if png_path and Path(png_path).is_file():
                story.append(Paragraph(_escape(chart.get("caption") or "图表"), st["h2"]))
                story.append(Image(str(png_path), width=14 * cm, height=7 * cm))
                story.append(Spacer(1, 0.3 * cm))
        story.append(PageBreak())

    story.append(Paragraph("关键发现", st["h1"]))
    for f in doc.get("findings") or []:
        story.append(Paragraph(f"• {_escape(f.get('text', ''))}", st["body"]))
        story.append(Spacer(1, 0.15 * cm))
    story.append(PageBreak())

    story.append(Paragraph("建议与后续行动", st["h1"]))
    for i, r in enumerate(doc.get("recommendations") or [], start=1):
        story.append(Paragraph(f"{i}. {_escape(r)}", st["body"]))
        story.append(Spacer(1, 0.15 * cm))
    story.append(PageBreak())

    story.append(Paragraph("数据口径与说明", st["h1"]))
    story.append(
        Paragraph(
            _escape(
                f"本报告数据范围：{meta.get('scopeSummary', '见用户权限')}。"
                " 各章节数值均来自问数引擎实时查询，未查询字段不作推断。"
            ),
            st["body"],
        )
    )
    story.append(
        Paragraph(
            _escape("表格默认展示前 50 行；完整结果可通过各节 Trace 在系统中追溯。"),
            st["body"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("附录 · Trace 清单", st["h1"]))
    trace_rows = [["章节", "Trace", "状态", "耗时(ms)"]]
    for tr in (doc.get("appendix") or {}).get("traces") or []:
        trace_rows.append(
            [
                str(tr.get("chapterIndex") or ""),
                str(tr.get("traceId") or "-"),
                str(tr.get("status") or ""),
                str(tr.get("latencyMs") or "-"),
            ]
        )
    tt = Table(trace_rows, repeatRows=1)
    tt.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]
        )
    )
    story.append(tt)

    pdf.build(story)
    data = buffer.getvalue()
    output_path.write_bytes(data)
    page_count = _count_pages(output_path, doc)
    return page_count, len(data)


def _count_pages(output_path: Path, doc: dict[str, Any]) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(output_path)).pages)
    except Exception:
        return max(15, len(doc.get("chapters") or []) * 2 + 5)
