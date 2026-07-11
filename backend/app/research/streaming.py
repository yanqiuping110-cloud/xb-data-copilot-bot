"""Research SSE 帧组装。"""

from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def report_started_event(report_id: str, title: str) -> str:
    return format_sse("report_started", {"reportId": report_id, "title": title})


def status_event(text: str, *, phase: str | None = None) -> str:
    body: dict[str, Any] = {"text": text}
    if phase:
        body["phase"] = phase
    return format_sse("status", body)


def heartbeat_event(elapsed_ms: int) -> str:
    return format_sse("heartbeat", {"elapsedMs": elapsed_ms})


def activity_event(level: str, message: str) -> str:
    return format_sse("activity", {"level": level, "message": message})


def plan_item_event(index: int, title: str, intent: str) -> str:
    return format_sse(
        "plan_item",
        {"index": index, "title": title, "intent": intent},
    )


def plan_revealed_event(sections: list[dict[str, Any]]) -> str:
    return format_sse("plan_revealed", {"sections": sections})


def section_start_event(section_index: int, title: str, question: str) -> str:
    return format_sse(
        "section_start",
        {"sectionIndex": section_index, "title": title, "question": question},
    )


def section_progress_event(
    section_index: int,
    *,
    pipeline_step: int,
    label: str,
    tool: str | None = None,
) -> str:
    body: dict[str, Any] = {
        "sectionIndex": section_index,
        "pipelineStep": pipeline_step,
        "label": label,
    }
    if tool:
        body["tool"] = tool
    return format_sse("section_progress", body)


def text_delta_event(scope: str, delta: str, *, section_index: int | None = None) -> str:
    body: dict[str, Any] = {"scope": scope, "delta": delta}
    if section_index is not None:
        body["sectionIndex"] = section_index
    return format_sse("text_delta", body)


def section_done_event(
    section_index: int,
    *,
    status: str,
    sub_trace_id: str | None,
    latency_ms: int | None,
    answer: str | None = None,
) -> str:
    body: dict[str, Any] = {
        "sectionIndex": section_index,
        "status": status,
        "subTraceId": sub_trace_id,
        "latencyMs": latency_ms,
    }
    if answer:
        body["answer"] = answer
    return format_sse("section_done", body)


def section_preview_event(section_index: int, columns: list, rows_sample: list) -> str:
    return format_sse(
        "section_preview",
        {"sectionIndex": section_index, "columns": columns, "rowsSample": rows_sample},
    )


def chart_ready_event(section_index: int, chart_spec: dict[str, Any]) -> str:
    return format_sse(
        "chart_ready",
        {"sectionIndex": section_index, "chartSpec": chart_spec},
    )


def insights_ready_event(
    executive_summary: str,
    insights: list[dict[str, Any]],
    recommendations: list[str],
) -> str:
    return format_sse(
        "insights_ready",
        {
            "executiveSummary": executive_summary,
            "insights": insights,
            "recommendations": recommendations,
        },
    )


def pdf_ready_event(pdf_url: str, page_count: int, file_size: int) -> str:
    return format_sse(
        "pdf_ready",
        {"pdfUrl": pdf_url, "pageCount": page_count, "fileSizeBytes": file_size},
    )


def report_done_event(payload: dict[str, Any]) -> str:
    return format_sse("report_done", payload)


def error_event(code: str, message: str) -> str:
    return format_sse("error", {"code": code, "message": message})
