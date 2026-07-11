"""Insight Engine · 深度分析报告 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.research import audit as research_audit
from app.research import cancel_registry
from app.research import repository as repo
from app.research.runner import ResearchError, get_report_detail, resolve_pdf_path
from app.research.service import handle_research_report, handle_research_stream, wants_stream
from app.schemas.research import ResearchBranchRequest, ResearchReportRequest, ResearchReportResponse
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def _ensure_enabled(settings: Settings) -> None:
    if not settings.research_enabled:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "RESEARCH_DISABLED", "message": "深度洞察功能未启用"}},
        )


@router.post(
    "/report",
    response_model=ResearchReportResponse,
    response_model_by_alias=True,
)
async def create_report(
    body: ResearchReportRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """创建并执行深度分析报告；options.stream=true 时返回 SSE。"""
    _ensure_enabled(settings)
    if wants_stream(body):
        return StreamingResponse(
            handle_research_stream(body, ctx, session, settings),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    try:
        return await handle_research_report(body, ctx, session, settings)
    except ResearchError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc


@router.post("/report/{report_id}/branch")
async def branch_report(
    report_id: str,
    body: ResearchBranchRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """从指定章节 fork 新报告（Phase 2 · 章节分支）。"""
    _ensure_enabled(settings)
    parent = await repo.get_report(session, report_id=report_id, user_id=ctx.user_id)
    if parent is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "来源报告不存在"}})
    req = ResearchReportRequest(
        request_text=body.request_text or parent.get("request_text") or "",
        session_id=body.session_id,
        template_code=body.template_code or parent.get("template_code"),
        options=body.options,
        parent_report_id=report_id,
        branch_from_section=body.branch_from_section,
    )
    if wants_stream(req):
        return StreamingResponse(
            handle_research_stream(req, ctx, session, settings),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    try:
        return await handle_research_report(req, ctx, session, settings)
    except ResearchError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc


@router.get("/report/{report_id}/traces")
async def list_report_traces(
    report_id: str,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """返回报告各节 Trace 清单（Trace 飞行记录仪数据源）。"""
    _ensure_enabled(settings)
    detail = await get_report_detail(session, report_id=report_id, user_id=ctx.user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "报告不存在"}})
    traces = []
    for s in detail.sections or []:
        traces.append(
            {
                "sectionIndex": s.section_index,
                "title": s.title,
                "subTraceId": s.sub_trace_id,
                "status": s.status,
                "latencyMs": s.latency_ms,
            }
        )
    return {"reportId": report_id, "traces": traces}


@router.post("/report/{report_id}/cancel")
async def cancel_report(
    report_id: str,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    _ensure_enabled(settings)
    row = await repo.get_report(session, report_id=report_id, user_id=ctx.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "报告不存在"}})
    if row.get("status") not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "NOT_CANCELLABLE", "message": "报告当前状态不可取消"}},
        )
    cancel_registry.request_cancel(report_id)
    await repo.mark_report_cancelled(session, report_id=report_id)
    await research_audit.log_research_event(
        session,
        ctx=ctx,
        report_id=report_id,
        action="REPORT_CANCEL",
        detail=row.get("title") or report_id,
    )
    await session.commit()
    return {"reportId": report_id, "status": "cancelled"}


@router.get("/report")
async def list_reports(
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    _ensure_enabled(settings)
    rows = await repo.list_reports(session, user_id=ctx.user_id, limit=20)
    return [
        {
            "reportId": r["report_id"],
            "title": r["title"],
            "status": r["status"],
            "sectionTotal": r.get("section_total"),
            "sectionDone": r.get("section_done"),
            "pdfPageCount": r.get("pdf_page_count"),
            "createdAt": r.get("created_at").isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]


@router.get(
    "/report/{report_id}",
    response_model=ResearchReportResponse,
    response_model_by_alias=True,
)
async def get_report(
    report_id: str,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    _ensure_enabled(settings)
    detail = await get_report_detail(session, report_id=report_id, user_id=ctx.user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "报告不存在"}})
    return detail


@router.get("/report/{report_id}/pdf")
@router.get("/report/{report_id}/download")
async def download_pdf(
    report_id: str,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    _ensure_enabled(settings)
    row = await repo.get_report(session, report_id=report_id, user_id=ctx.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "报告不存在"}})
    path = resolve_pdf_path(settings, report_id)
    if path is None and row.get("report_pdf_path"):
        from pathlib import Path

        alt = Path(row["report_pdf_path"])
        path = alt if alt.is_file() else None
    if path is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "PDF_NOT_FOUND", "message": "PDF 尚未生成"}})
    await research_audit.log_research_event(
        session,
        ctx=ctx,
        report_id=report_id,
        action="REPORT_DOWNLOAD",
        detail=row.get("title") or report_id,
    )
    await session.commit()
    filename = f"{report_id}.pdf"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
