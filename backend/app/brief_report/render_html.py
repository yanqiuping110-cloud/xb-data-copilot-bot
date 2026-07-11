"""BriefReportDocument → HTML。"""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.brief_report.assets import enrich_doc_assets
from app.brief_report.theme import TEMPLATES_DIR


def render_brief_report_html(doc: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    css_path = TEMPLATES_DIR / "brief_report.css"
    css_text = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    theme = doc.get("theme") or {}
    typography = theme.get("typography") or {}
    template = env.get_template("brief_report.html")
    enriched = enrich_doc_assets(doc)
    return template.render(
        doc=enriched,
        report_css=css_text,
        accent_color=typography.get("accentColor") or "#22c55e",
    )
