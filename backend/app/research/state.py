"""Research LangGraph 状态。"""

from __future__ import annotations

from typing import Any, TypedDict


class ResearchGraphState(TypedDict, total=False):
    report_id: str
    request_text: str
    template_code: str | None
    plan: dict[str, Any]
    section_index: int
    section_results: list[dict[str, Any]]
    report_doc: dict[str, Any]
    pdf_path: str | None
    pdf_url: str | None
    pdf_page_count: int | None
    pdf_file_size: int | None
    status: str
    error_code: str | None
    parent_report_id: str | None
    branch_from_section: int | None
