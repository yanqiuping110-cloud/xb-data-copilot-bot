"""ReportDocument → HTML。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.research.theme import ASSETS_DIR, TEMPLATES_DIR


def render_report_html(doc: dict[str, Any], *, include_cover_svg: bool = True) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    cover_svg = ""
    if include_cover_svg:
        svg_path = ASSETS_DIR / "cover-bg.svg"
        if svg_path.is_file():
            cover_svg = svg_path.read_text(encoding="utf-8")
    template = env.get_template("report_long.html")
    css_path = TEMPLATES_DIR / "report_styles.css"
    css_text = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    html = template.render(doc=doc, cover_svg=cover_svg, report_css=css_text)
    return html
