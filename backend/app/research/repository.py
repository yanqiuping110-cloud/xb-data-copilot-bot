"""copilot_research_report / section 持久化。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create_report(
    session: AsyncSession,
    *,
    report_id: str,
    user_id: int,
    title: str,
    request_text: str,
    template_code: str | None,
    session_id: str | None = None,
    parent_report_id: str | None = None,
    branch_from_section: int | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO copilot_research_report (
                report_id, user_id, session_id, title, request_text,
                template_code, parent_report_id, branch_from_section,
                status, section_total, section_done
            ) VALUES (
                :report_id, :user_id, :session_id, :title, :request_text,
                :template_code, :parent_report_id, :branch_from_section,
                'pending', 0, 0
            )
            """
        ),
        {
            "report_id": report_id,
            "user_id": user_id,
            "session_id": session_id,
            "title": title,
            "request_text": request_text,
            "template_code": template_code,
            "parent_report_id": parent_report_id,
            "branch_from_section": branch_from_section,
        },
    )


async def update_report_plan(
    session: AsyncSession,
    *,
    report_id: str,
    plan: dict[str, Any],
    section_total: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE copilot_research_report
            SET plan_json = :plan_json, section_total = :section_total,
                status = 'running', updated_at = NOW()
            WHERE report_id = :report_id AND deleted = 0
            """
        ),
        {
            "report_id": report_id,
            "plan_json": json.dumps(plan, ensure_ascii=False),
            "section_total": section_total,
        },
    )


async def insert_sections(
    session: AsyncSession,
    *,
    report_id: str,
    sections: list[dict[str, Any]],
) -> None:
    for s in sections:
        await session.execute(
            text(
                """
                INSERT INTO copilot_research_section (
                    report_id, section_index, title, question, intent, status
                ) VALUES (
                    :report_id, :section_index, :title, :question, :intent, 'pending'
                )
                """
            ),
            {
                "report_id": report_id,
                "section_index": s["index"],
                "title": s["title"],
                "question": s["question"],
                "intent": s.get("intent"),
            },
        )


async def update_section_result(
    session: AsyncSession,
    *,
    report_id: str,
    section_index: int,
    status: str,
    answer: str | None = None,
    columns: list[str] | None = None,
    rows: list[list] | None = None,
    chart_spec: dict | None = None,
    sub_trace_id: str | None = None,
    error_code: str | None = None,
    latency_ms: int | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE copilot_research_section SET
                status = :status, answer = :answer,
                columns_json = :columns_json, rows_json = :rows_json,
                chart_spec_json = :chart_spec_json,
                sub_trace_id = :sub_trace_id, error_code = :error_code,
                latency_ms = :latency_ms, updated_at = NOW()
            WHERE report_id = :report_id AND section_index = :section_index
            """
        ),
        {
            "report_id": report_id,
            "section_index": section_index,
            "status": status,
            "answer": answer,
            "columns_json": json.dumps(columns, ensure_ascii=False) if columns else None,
            "rows_json": json.dumps(rows, ensure_ascii=False) if rows else None,
            "chart_spec_json": json.dumps(chart_spec, ensure_ascii=False) if chart_spec else None,
            "sub_trace_id": sub_trace_id,
            "error_code": error_code,
            "latency_ms": latency_ms,
        },
    )
    await session.execute(
        text(
            """
            UPDATE copilot_research_report
            SET section_done = (
                SELECT COUNT(*) FROM copilot_research_section
                WHERE report_id = :report_id AND deleted = 0
                  AND status IN ('success', 'fail', 'skipped')
            ), updated_at = NOW()
            WHERE report_id = :report_id
            """
        ),
        {"report_id": report_id},
    )


async def finish_report(
    session: AsyncSession,
    *,
    report_id: str,
    status: str,
    report_doc: dict[str, Any] | None,
    pdf_path: str | None,
    pdf_url: str | None,
    pdf_page_count: int | None,
    pdf_file_size: int | None,
    latency_ms: int | None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE copilot_research_report SET
                status = :status,
                report_doc_json = :report_doc_json,
                report_pdf_path = :pdf_path,
                report_pdf_url = :pdf_url,
                pdf_page_count = :pdf_page_count,
                pdf_file_size = :pdf_file_size,
                pdf_generated_at = IF(:pdf_path IS NOT NULL, NOW(), pdf_generated_at),
                latency_ms_total = :latency_ms,
                error_code = :error_code,
                error_message = :error_message,
                updated_at = NOW()
            WHERE report_id = :report_id
            """
        ),
        {
            "report_id": report_id,
            "status": status,
            "report_doc_json": json.dumps(report_doc, ensure_ascii=False) if report_doc else None,
            "pdf_path": pdf_path,
            "pdf_url": pdf_url,
            "pdf_page_count": pdf_page_count,
            "pdf_file_size": pdf_file_size,
            "latency_ms": latency_ms,
            "error_code": error_code,
            "error_message": error_message,
        },
    )


async def get_report(
    session: AsyncSession,
    *,
    report_id: str,
    user_id: int,
) -> dict[str, Any] | None:
    r = await session.execute(
        text(
            """
            SELECT report_id, user_id, title, request_text, template_code,
                   parent_report_id, branch_from_section, plan_json,
                   status, section_total, section_done, report_doc_json,
                   report_pdf_path, report_pdf_url, pdf_page_count, pdf_file_size,
                   latency_ms_total, error_code, error_message, created_at
            FROM copilot_research_report
            WHERE report_id = :report_id AND user_id = :user_id AND deleted = 0
            LIMIT 1
            """
        ),
        {"report_id": report_id, "user_id": user_id},
    )
    row = r.mappings().first()
    if not row:
        return None
    return dict(row)


async def list_sections(
    session: AsyncSession,
    *,
    report_id: str,
) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            """
            SELECT section_index, title, question, intent, status, answer,
                   sub_trace_id, error_code, latency_ms
            FROM copilot_research_section
            WHERE report_id = :report_id AND deleted = 0
            ORDER BY section_index ASC
            """
        ),
        {"report_id": report_id},
    )
    return [dict(row) for row in r.mappings()]


async def list_reports(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            """
            SELECT report_id, title, status, section_total, section_done,
                   pdf_page_count, latency_ms_total, created_at, updated_at
            FROM copilot_research_report
            WHERE user_id = :user_id AND deleted = 0
            ORDER BY updated_at DESC
            LIMIT :limit
            """
        ),
        {"user_id": user_id, "limit": limit},
    )
    return [dict(row) for row in r.mappings()]


async def count_running_reports(session: AsyncSession, *, user_id: int) -> int:
    r = await session.execute(
        text(
            """
            SELECT COUNT(*) AS cnt FROM copilot_research_report
            WHERE user_id = :user_id AND deleted = 0
              AND status IN ('pending', 'running')
            """
        ),
        {"user_id": user_id},
    )
    row = r.mappings().first()
    return int(row["cnt"]) if row else 0


async def mark_report_cancelled(session: AsyncSession, *, report_id: str) -> None:
    await session.execute(
        text(
            """
            UPDATE copilot_research_report
            SET status = 'cancelled', updated_at = NOW()
            WHERE report_id = :report_id AND deleted = 0
            """
        ),
        {"report_id": report_id},
    )
