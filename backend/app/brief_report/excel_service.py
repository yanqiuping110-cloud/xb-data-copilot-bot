"""问数 Excel 导出编排。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.brief_report.export_excel import export_turns_excel
from app.brief_report.loader import BriefReportLoadError, load_turns
from app.brief_report.service import BriefReportError, _validate_session
from app.brief_report.sheet_names_llm import plan_excel_sheet_names
from app.core.context import UserContext
from app.schemas.brief_report import BriefReportExcelRequest
from config.settings import Settings, get_settings


def excel_download_filename() -> str:
    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    return f"问数导出_{stamp}.xlsx"


def content_disposition(filename: str) -> str:
    ascii_name = "ask-export.xlsx"
    encoded = quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


async def handle_brief_report_excel(
    body: BriefReportExcelRequest,
    ctx: UserContext,
    db: AsyncSession,
    settings: Settings | None = None,
) -> tuple[bytes, str]:
    """加载 turns、命名 sheet、写出 xlsx。返回 (bytes, filename)。"""
    cfg = settings or get_settings()
    if not cfg.brief_report_enabled:
        raise BriefReportError("BRIEF_REPORT_DISABLED", "报告分析功能未启用", 503)

    trace_ids = list(body.trace_ids or [])
    if not trace_ids:
        raise BriefReportError("EMPTY_TRACE_IDS", "请至少勾选一条问数记录", 400)
    if len(trace_ids) > cfg.brief_report_max_chapters:
        raise BriefReportError(
            "TOO_MANY_CHAPTERS",
            f"最多勾选 {cfg.brief_report_max_chapters} 条问数记录",
            400,
        )

    await _validate_session(db, cfg, session_id=body.session_id, user_id=ctx.user_id)

    try:
        turns = await load_turns(
            db,
            session_id=body.session_id,
            user_id=ctx.user_id,
            trace_ids=trace_ids,
        )
    except BriefReportLoadError as exc:
        raise BriefReportError(exc.code, exc.message, exc.status_code) from exc

    sheet_names = await plan_excel_sheet_names(turns, settings=cfg)
    try:
        data = export_turns_excel(turns, sheet_names)
    except Exception as exc:
        raise BriefReportError("EXPORT_FAILED", f"Excel 导出失败：{exc}", 500) from exc

    return data, excel_download_filename()
