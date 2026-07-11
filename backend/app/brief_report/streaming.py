"""Brief Report SSE 帧组装。"""

from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def status_event(text: str, *, phase: str | None = None) -> str:
    body: dict[str, Any] = {"text": text}
    if phase:
        body["phase"] = phase
    return format_sse("status", body)


def progress_event(step: int, label: str) -> str:
    return format_sse("progress", {"step": step, "label": label})


def report_done_event(
    report_id: str,
    *,
    pdf_url: str,
    page_count: int,
    file_size: int,
) -> str:
    return format_sse(
        "report_done",
        {
            "reportId": report_id,
            "pdfUrl": pdf_url,
            "pageCount": page_count,
            "fileSize": file_size,
        },
    )


def error_event(code: str, message: str) -> str:
    return format_sse("error", {"code": code, "message": message})
