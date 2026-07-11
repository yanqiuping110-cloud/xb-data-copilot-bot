"""A4 竖版精美 PDF（ReportLab Canvas，Windows 无 WeasyPrint 时主路径）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

_FONT = "STSong-Light"
_GREEN = colors.HexColor("#22c55e")
_DARK = colors.HexColor("#0f172a")
_MUTED = colors.HexColor("#64748b")
_LIGHT_BG = colors.HexColor("#f8fafc")


def _ensure_font() -> str:
    try:
        pdfmetrics.getFont(_FONT)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
    return _FONT


def _esc(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _p(text: str, **kw) -> Paragraph:
    font = _ensure_font()
    style = ParagraphStyle("p", fontName=font, **kw)
    return Paragraph(_esc(text), style)


def _draw_bg_image(c: canvas.Canvas, path: str | None, w: float, h: float) -> None:
    if not path or not Path(path).is_file():
        return
    try:
        c.drawImage(str(path), 0, 0, width=w, height=h, preserveAspectRatio=False, mask="auto")
    except Exception:
        pass


def _draw_cover(c: canvas.Canvas, doc: dict[str, Any], w: float, h: float) -> None:
    cover = doc.get("cover") or {}
    _draw_bg_image(c, cover.get("backgroundPath"), w, h)

    c.saveState()
    c.setFillColor(colors.white)
    c.setFillAlpha(0.78)
    c.rect(0, 0, w, h * 0.55, fill=1, stroke=0)
    c.restoreState()

    margin = 18 * mm
    y = h - 88 * mm
    title = cover.get("title") or "数据分析汇报"
    title_p = _p(title, fontSize=28, leading=38, textColor=_DARK, alignment=2)
    tw, th = title_p.wrap(w - 2 * margin, 90 * mm)
    title_p.drawOn(c, margin, y - th)
    y -= th + 5 * mm

    subtitle = (cover.get("subtitle") or "").strip()
    if subtitle:
        sub_p = _p(subtitle, fontSize=14, leading=20, textColor=_MUTED, alignment=2)
        sw, sh = sub_p.wrap(w - 2 * margin, 30 * mm)
        sub_p.drawOn(c, margin, y - sh)
        y -= sh + 6 * mm

    c.setFillColor(_GREEN)
    c.rect(w - margin - 52 * mm, y, 52 * mm, 3.5, fill=1, stroke=0)

    meta_y = 30 * mm
    if cover.get("org"):
        org_p = _p(f"汇报单位：{cover['org']}", fontSize=13, leading=18, textColor=_MUTED, alignment=2)
        ow, oh = org_p.wrap(w - 2 * margin, 24 * mm)
        org_p.drawOn(c, margin, meta_y + oh)
        meta_y += oh + 4 * mm
    date_p = _p(
        f"汇报时间：{cover.get('date') or ''}",
        fontSize=13,
        leading=18,
        textColor=_MUTED,
        alignment=2,
    )
    dw, dh = date_p.wrap(w - 2 * margin, 24 * mm)
    date_p.drawOn(c, margin, meta_y + dh)


def _draw_toc_page(c: canvas.Canvas, items: list[dict[str, Any]], w: float, h: float, *, show_header: bool) -> None:
    margin = 16 * mm
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.rect(0, 0, w, h, fill=1, stroke=0)

    c.saveState()
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    for i in range(4):
        c.line(w * 0.45 + i * 18, h, w * 0.95, h * (0.15 + i * 0.12))
    c.restoreState()

    y = h - 24 * mm
    if show_header:
        c.setFont(_FONT, 32)
        c.setFillColor(_DARK)
        c.drawString(margin, y, "目录")
        c.setFont(_FONT, 16)
        c.setFillColor(colors.HexColor("#94a3b8"))
        c.drawString(margin + 26 * mm, y + 1.5 * mm, "CONTENTS")
        y -= 12 * mm
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.line(margin, y, w - margin, y)
        y -= 14 * mm
    else:
        y -= 6 * mm

    col_w = (w - 2 * margin - 8 * mm) / 2
    left_x = margin
    right_x = margin + col_w + 8 * mm
    row_h = 36 * mm
    start_y = y

    for i, item in enumerate(items):
        col = i % 2
        row = i // 2
        x = left_x if col == 0 else right_x
        item_y = start_y - row * row_h

        c.setFont(_FONT, 22)
        c.setFillColor(_GREEN)
        c.drawString(x, item_y, item.get("code") or f"{i+1:02d}")

        title = item.get("title") or ""
        title_p = _p(title, fontSize=13, leading=17, textColor=_DARK)
        tw, th = title_p.wrap(col_w - 16 * mm, 18 * mm)
        title_p.drawOn(c, x + 16 * mm, item_y - 2 * mm)

        summary = item.get("summary") or ""
        sum_p = _p(summary, fontSize=10, leading=14, textColor=_MUTED)
        sw, sh = sum_p.wrap(col_w - 16 * mm, 20 * mm)
        sum_p.drawOn(c, x + 16 * mm, item_y - th - 7 * mm - sh)



def _draw_toc(c: canvas.Canvas, doc: dict[str, Any], w: float, h: float) -> None:
    """保留兼容；分页逻辑已移至 export 主流程。"""
    _draw_toc_page(c, doc.get("toc") or [], w, h, show_header=True)



def _draw_chapter(c: canvas.Canvas, ch: dict[str, Any], w: float, h: float) -> None:
    margin = 16 * mm
    inner_w = w - 2 * margin

    c.setFillColor(colors.HexColor("#f8fafc"))
    c.rect(0, 0, w, h, fill=1, stroke=0)

    c.saveState()
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.4)
    for i in range(6):
        c.line(w * 0.5 + i * 12, h, w - margin, h * (0.08 + i * 0.1))
    c.restoreState()

    # 章节标题：与目录条目同款（绿色序号 + 深色标题，无色带）
    y = h - 22 * mm
    idx = ch.get("index") or 1
    c.setFont(_FONT, 18)
    c.setFillColor(_GREEN)
    c.drawString(margin, y, f"{idx:02d}")

    title = ch.get("title") or ch.get("question") or ""
    title_p = _p(title, fontSize=10.5, leading=14, textColor=_DARK)
    tw, th = title_p.wrap(inner_w - 14 * mm, 22 * mm)
    title_p.drawOn(c, margin + 14 * mm, y - 2 * mm)

    y -= max(th, 16) + 8 * mm
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.5)
    c.line(margin, y, w - margin, y)
    y -= 12 * mm

    label2 = _p("数据洞察", fontSize=11, textColor=colors.HexColor("#16a34a"))
    l2w, l2h = label2.wrap(40 * mm, 10 * mm)
    label2.drawOn(c, margin, y)
    y -= l2h + 5 * mm

    answer = ch.get("answer") or ""
    paras = [p.strip() for p in answer.split("\n") if p.strip()]
    if paras:
        c.setFillColor(colors.white)
        card_top = y
        card_h_est = min(55 * mm, 12 * mm * len(paras))
        c.roundRect(margin, card_top - card_h_est - 6 * mm, inner_w, card_h_est + 10 * mm, 4, fill=1, stroke=0)
        c.setFillColor(_GREEN)
        c.rect(margin, card_top - card_h_est - 6 * mm, 3, card_h_est + 10 * mm, fill=1, stroke=0)

        text_y = card_top - 4 * mm
        for para in paras:
            a_p = _p(para, fontSize=10, leading=15, textColor=colors.HexColor("#334155"))
            aw, ah = a_p.wrap(inner_w - 10 * mm, 80 * mm)
            if text_y - ah < 35 * mm:
                break
            a_p.drawOn(c, margin + 6 * mm, text_y - ah)
            text_y -= ah + 3 * mm
        y = text_y - 8 * mm
    else:
        y -= 4 * mm

    chart = ch.get("chartPngPath")
    if chart and Path(chart).is_file() and y > 55 * mm:
        try:
            img_h = min(78 * mm, y - 40 * mm)
            c.setFillColor(colors.white)
            c.roundRect(margin, y - img_h - 8 * mm, inner_w, img_h + 12 * mm, 4, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.roundRect(margin, y - img_h - 8 * mm, inner_w, img_h + 12 * mm, 4, fill=0, stroke=1)
            c.drawImage(
                str(chart),
                margin + 4 * mm,
                y - img_h - 4 * mm,
                width=inner_w - 8 * mm,
                height=img_h,
                preserveAspectRatio=True,
                anchor="c",
            )
            y -= img_h + 16 * mm
        except Exception:
            pass

    tbl = ch.get("table") or {}
    cols = tbl.get("columns") or []
    rows = tbl.get("rows") or []
    if cols and rows and y > 45 * mm:
        t_p = _p("数据明细", fontSize=11, textColor=_DARK)
        ttw, tth = t_p.wrap(40 * mm, 10 * mm)
        t_p.drawOn(c, margin, y - tth + 2 * mm)
        y -= tth + 6 * mm
        data = [cols] + [[str(cell) for cell in row] for row in rows[:12]]
        table = Table(data, repeatRows=1, colWidths=[inner_w / max(len(cols), 1)] * len(cols))
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        tw, th = table.wrap(inner_w, y)
        if y - th > 18 * mm:
            table.drawOn(c, margin, y - th)


def _draw_ending(c: canvas.Canvas, doc: dict[str, Any], w: float, h: float) -> None:
    ending = doc.get("ending") or {}
    _draw_bg_image(c, ending.get("backgroundPath"), w, h)

    c.saveState()
    c.setFillColor(colors.white)
    c.setFillAlpha(0.42)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.restoreState()

    headline = ending.get("headline") or "感谢聆听"
    h_p = _p(headline, fontSize=36, leading=46, textColor=_DARK, alignment=1)
    hw, hh = h_p.wrap(w - 36 * mm, 50 * mm)
    h_p.drawOn(c, 18 * mm, h / 2 + 22 * mm)

    message = ending.get("message") or ""
    m_p = _p(
        message,
        fontSize=14,
        leading=22,
        textColor=colors.HexColor("#334155"),
        alignment=1,
    )
    mw, mh = m_p.wrap(w - 44 * mm, 80 * mm)
    m_p.drawOn(c, 22 * mm, h / 2 - mh - 8 * mm)


def export_brief_report_pdf_canvas(doc: dict[str, Any], output_path: Path) -> tuple[int, int]:
    """Canvas 导出，支持全页背景图与精美版式。"""
    _ensure_font()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = A4
    c = canvas.Canvas(str(output_path), pagesize=A4)
    page_count = 0

    _draw_cover(c, doc, w, h)
    c.showPage()
    page_count += 1

    toc = doc.get("toc") or []
    per_page = 6
    toc_chunks = [toc[i : i + per_page] for i in range(0, max(len(toc), 1), per_page)] or [[]]
    for idx, chunk in enumerate(toc_chunks):
        _draw_toc_page(c, chunk, w, h, show_header=idx == 0)
        c.showPage()
        page_count += 1

    for ch in doc.get("chapters") or []:
        _draw_chapter(c, ch, w, h)
        c.showPage()
        page_count += 1

    _draw_ending(c, doc, w, h)
    c.showPage()
    page_count += 1

    c.save()
    data = output_path.read_bytes()
    return page_count, len(data)
