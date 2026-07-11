"""copilot_brief_report 持久化。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create_report(
    session: AsyncSession,
    *,
    report_id: str,
    user_id: int,
    session_id: str,
    trace_ids: list[str],
    user_prompt: str,
    status: str = "pending",
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO copilot_brief_report (
                report_id, user_id, session_id, trace_ids_json, user_prompt, status
            ) VALUES (
                :report_id, :user_id, :session_id, :trace_ids_json, :user_prompt, :status
            )
            """
        ),
        {
            "report_id": report_id,
            "user_id": user_id,
            "session_id": session_id,
            "trace_ids_json": json.dumps(trace_ids, ensure_ascii=False),
            "user_prompt": user_prompt,
            "status": status,
        },
    )


async def mark_report_done(
    session: AsyncSession,
    *,
    report_id: str,
    pdf_path: str,
    doc_json: dict[str, Any],
    page_count: int,
    file_size: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE copilot_brief_report
            SET status = 'done',
                pdf_path = :pdf_path,
                doc_json = :doc_json,
                pdf_page_count = :page_count,
                pdf_file_size = :file_size,
                updated_at = NOW()
            WHERE report_id = :report_id AND deleted = 0
            """
        ),
        {
            "report_id": report_id,
            "pdf_path": pdf_path,
            "doc_json": json.dumps(doc_json, ensure_ascii=False),
            "page_count": page_count,
            "file_size": file_size,
        },
    )


async def mark_report_failed(
    session: AsyncSession,
    *,
    report_id: str,
    error_code: str,
    error_message: str,
) -> None:
    await session.execute(
        text(
            """
            UPDATE copilot_brief_report
            SET status = 'fail',
                error_code = :error_code,
                error_message = :error_message,
                updated_at = NOW()
            WHERE report_id = :report_id AND deleted = 0
            """
        ),
        {
            "report_id": report_id,
            "error_code": error_code,
            "error_message": error_message[:512],
        },
    )


async def get_report(
    session: AsyncSession,
    *,
    report_id: str,
    user_id: int,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT report_id, user_id, session_id, trace_ids_json, user_prompt,
                   status, pdf_path, doc_json, pdf_page_count, pdf_file_size,
                   error_code, error_message, created_at, updated_at
            FROM copilot_brief_report
            WHERE report_id = :report_id AND user_id = :user_id AND deleted = 0
            """
        ),
        {"report_id": report_id, "user_id": user_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    data = dict(row)
    if data.get("trace_ids_json"):
        try:
            data["trace_ids"] = json.loads(data["trace_ids_json"])
        except json.JSONDecodeError:
            data["trace_ids"] = []
    if data.get("doc_json"):
        try:
            data["doc"] = json.loads(data["doc_json"])
        except json.JSONDecodeError:
            data["doc"] = None
    return data


async def list_reports(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            SELECT report_id, session_id, user_prompt, status,
                   pdf_page_count, pdf_file_size, created_at
            FROM copilot_brief_report
            WHERE user_id = :user_id AND deleted = 0
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"user_id": user_id, "limit": limit},
    )
    return [dict(r) for r in result.mappings()]
