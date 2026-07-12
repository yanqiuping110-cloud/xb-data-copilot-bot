"""Brief Report API 模型。"""

from __future__ import annotations

from typing import Any

from app.schemas.base import CamelModel


class BriefReportOptions(CamelModel):
    title: str | None = None
    subtitle: str | None = None
    org: str | None = None
    report_date: str | None = None
    ending_message: str | None = None
    cover_background: str | None = None
    ending_background: str | None = None
    theme: str | None = None
    page_layout: str | None = None
    include_sql_appendix: bool = False
    stream: bool = False


class BriefReportRequest(CamelModel):
    session_id: str
    trace_ids: list[str]
    user_prompt: str
    options: BriefReportOptions | None = None


class BriefReportResponse(CamelModel):
    report_id: str
    status: str
    pdf_url: str | None = None
    pdf_page_count: int | None = None
    pdf_file_size: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    toc: list[dict[str, Any]] | None = None


class BriefReportListItem(CamelModel):
    report_id: str
    session_id: str
    user_prompt: str
    status: str
    pdf_page_count: int | None = None
    pdf_file_size: int | None = None
    created_at: str | None = None


class BriefReportExcelRequest(CamelModel):
    session_id: str
    trace_ids: list[str]
