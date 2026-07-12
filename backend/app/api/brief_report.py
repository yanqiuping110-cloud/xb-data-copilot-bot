"""问数 · 报告分析 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.brief_report.backgrounds import list_backgrounds, resolve_background_path
from app.brief_report import repository as repo
from app.brief_report.excel_service import content_disposition, handle_brief_report_excel
from app.brief_report.service import (
    BriefReportError,
    handle_brief_report,
    handle_brief_report_stream,
    pdf_url,
    resolve_pdf_path,
    wants_stream,
)
from app.core.context import UserContext
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.schemas.brief_report import (
    BriefReportExcelRequest,
    BriefReportListItem,
    BriefReportRequest,
    BriefReportResponse,
)
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/ask/brief-report", tags=["brief-report"])


def _ensure_enabled(settings: Settings) -> None:
    if not settings.brief_report_enabled:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "BRIEF_REPORT_DISABLED", "message": "报告分析功能未启用"}},
        )


@router.get("/backgrounds")
async def get_backgrounds(
    settings: Annotated[Settings, Depends(get_settings)],
    ctx: Annotated[UserContext, Depends(get_current_user)],
):
    _ensure_enabled(settings)
    return list_backgrounds(settings=settings)


@router.get("/backgrounds/file")
async def get_background_file(
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
    ctx: Annotated[UserContext, Depends(get_current_user)],
):
    _ensure_enabled(settings)
    resolved = resolve_background_path(path, settings=settings)
    if resolved is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "背景图不存在"}})
    return FileResponse(resolved)


@router.post("", response_model=BriefReportResponse, response_model_by_alias=True)
async def create_brief_report(
    body: BriefReportRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """生成报告分析 PDF；options.stream=true 时返回 SSE。"""
    _ensure_enabled(settings)
    if wants_stream(body):
        return StreamingResponse(
            handle_brief_report_stream(body, ctx, session, settings),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    try:
        return await handle_brief_report(body, ctx, session, settings)
    except BriefReportError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc


@router.post("/export-excel")
async def export_brief_report_excel(
    body: BriefReportExcelRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """将勾选的问数记录导出为多 Sheet Excel。"""
    _ensure_enabled(settings)
    try:
        data, filename = await handle_brief_report_excel(body, ctx, session, settings)
    except BriefReportError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("", response_model=list[BriefReportListItem], response_model_by_alias=True)
async def list_brief_reports(
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    _ensure_enabled(settings)
    rows = await repo.list_reports(session, user_id=ctx.user_id, limit=20)
    return [
        BriefReportListItem(
            report_id=r["report_id"],
            session_id=r["session_id"],
            user_prompt=r["user_prompt"],
            status=r["status"],
            pdf_page_count=r.get("pdf_page_count"),
            pdf_file_size=r.get("pdf_file_size"),
            created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        )
        for r in rows
    ]


@router.get("/{report_id}", response_model=BriefReportResponse, response_model_by_alias=True)
async def get_brief_report(
    report_id: str,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    _ensure_enabled(settings)
    row = await repo.get_report(session, report_id=report_id, user_id=ctx.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "报告不存在"}})
    doc = row.get("doc") or {}
    return BriefReportResponse(
        report_id=row["report_id"],
        status=row["status"],
        pdf_url=pdf_url(settings, report_id) if row.get("pdf_path") else None,
        pdf_page_count=row.get("pdf_page_count"),
        pdf_file_size=row.get("pdf_file_size"),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        toc=doc.get("toc"),
    )


@router.get("/{report_id}/pdf")
async def download_brief_report_pdf(
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
    if path is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "PDF_NOT_READY", "message": "PDF 尚未生成"}})
    return FileResponse(path, media_type="application/pdf", filename=f"{report_id}.pdf")
