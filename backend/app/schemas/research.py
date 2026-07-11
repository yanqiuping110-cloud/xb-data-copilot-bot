"""深度分析报告 API 模型。"""

from __future__ import annotations

from typing import Any

from app.schemas.base import CamelModel


class ResearchOptions(CamelModel):
    stream: bool = False
    demo_pace: bool = False


class ResearchSectionPlan(CamelModel):
    title: str
    question: str
    intent: str | None = "open_query"


class ResearchReportRequest(CamelModel):
    request_text: str
    session_id: str | None = None
    template_code: str | None = "monthly_ops"
    options: ResearchOptions | None = None
    sections: list[ResearchSectionPlan] | None = None
    parent_report_id: str | None = None
    branch_from_section: int | None = None


class ResearchBranchRequest(CamelModel):
    request_text: str | None = None
    branch_from_section: int
    template_code: str | None = None
    session_id: str | None = None
    options: ResearchOptions | None = None


class ResearchSectionResponse(CamelModel):
    section_index: int
    title: str
    question: str
    intent: str | None = None
    status: str
    answer: str | None = None
    sub_trace_id: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None


class ResearchReportResponse(CamelModel):
    report_id: str
    status: str
    title: str
    section_total: int = 0
    section_done: int = 0
    pdf_url: str | None = None
    pdf_page_count: int | None = None
    pdf_file_size: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    sections: list[ResearchSectionResponse] | None = None
    insights: list[dict[str, Any]] | None = None
    executive_summary: str | None = None
