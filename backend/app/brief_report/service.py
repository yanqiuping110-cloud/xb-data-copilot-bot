"""报告分析流水线编排。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.brief_report import repository as repo
from app.brief_report.builder import build_brief_report_document
from app.brief_report.export_pdf import export_brief_report_pdf
from app.brief_report.loader import BriefReportLoadError, load_turns
from app.brief_report.planner_llm import plan_brief_report_copy
from app.brief_report import streaming as sse
from app.core.context import UserContext
from app.memory.session_service import SessionService, SessionError
from app.schemas.brief_report import BriefReportRequest, BriefReportResponse
from config.settings import Settings, get_settings


class BriefReportError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _storage_dir(settings: Settings) -> Path:
    path = Path(settings.brief_report_storage_dir)
    if path.is_absolute():
        return path
    from config.settings import ROOT_DIR

    return ROOT_DIR / path


def resolve_pdf_path(settings: Settings, report_id: str) -> Path | None:
    path = _storage_dir(settings) / f"{report_id}.pdf"
    return path if path.is_file() else None


def pdf_url(settings: Settings, report_id: str) -> str:
    prefix = (settings.brief_report_pdf_url_prefix or "/api/v1/ask/brief-report").rstrip("/")
    return f"{prefix}/{report_id}/pdf"


def wants_stream(body: BriefReportRequest) -> bool:
    return bool(body.options and body.options.stream)


def _options_dict(body: BriefReportRequest) -> dict[str, Any]:
    if not body.options:
        return {}
    return body.options.model_dump(by_alias=False, exclude={"stream"})


async def _validate_session(
    session: AsyncSession,
    settings: Settings,
    *,
    session_id: str,
    user_id: int,
) -> None:
    svc = SessionService(session, settings)
    try:
        if not await svc.verify_owner(session_id, user_id):
            raise BriefReportError("FORBIDDEN", "无权访问该对话", 403)
    except SessionError as exc:
        raise BriefReportError(exc.code, exc.message, exc.status_code) from exc


async def _run_pipeline(
    body: BriefReportRequest,
    ctx: UserContext,
    db: AsyncSession,
    settings: Settings,
    *,
    emit: Any | None = None,
) -> BriefReportResponse:
    if not settings.brief_report_enabled:
        raise BriefReportError("BRIEF_REPORT_DISABLED", "报告分析功能未启用", 503)

    user_prompt = (body.user_prompt or "").strip()
    if len(user_prompt) < 10:
        raise BriefReportError("INVALID_PROMPT", "报告提示词至少 10 字", 400)

    trace_ids = list(body.trace_ids or [])
    if len(trace_ids) > settings.brief_report_max_chapters:
        raise BriefReportError(
            "TOO_MANY_CHAPTERS",
            f"最多勾选 {settings.brief_report_max_chapters} 条问数记录",
            400,
        )

    opts = _options_dict(body)
    if opts.get("include_sql_appendix") and ctx.role != "ADMIN":
        raise BriefReportError("FORBIDDEN", "SQL 附录仅管理员可用", 403)

    await _validate_session(db, settings, session_id=body.session_id, user_id=ctx.user_id)

    async def step(n: int, label: str) -> None:
        if emit:
            await emit(sse.progress_event(n, label))
            await emit(sse.status_event(label, phase=f"step_{n}"))

    await step(1, "加载问数记录")
    try:
        turns = await load_turns(
            db,
            session_id=body.session_id,
            user_id=ctx.user_id,
            trace_ids=trace_ids,
        )
    except BriefReportLoadError as exc:
        raise BriefReportError(exc.code, exc.message, exc.status_code) from exc

    await step(2, "生成封面与目录文案")
    llm_plan = await plan_brief_report_copy(
        user_prompt=user_prompt,
        turns=turns,
        settings=settings,
    )

    report_id = f"brpt-{uuid4().hex[:16]}"
    work_dir = _storage_dir(settings) / report_id
    work_dir.mkdir(parents=True, exist_ok=True)

    await repo.create_report(
        db,
        report_id=report_id,
        user_id=ctx.user_id,
        session_id=body.session_id,
        trace_ids=trace_ids,
        user_prompt=user_prompt,
        status="pending",
    )
    await db.commit()

    try:
        await step(3, "组装报告内容")
        doc = build_brief_report_document(
            session_id=body.session_id,
            user_prompt=user_prompt,
            turns=turns,
            options=opts,
            llm_plan=llm_plan,
            work_dir=work_dir,
            settings=settings,
        )
        doc["meta"]["reportId"] = report_id

        await step(4, "渲染图表")
        await step(5, "导出 PDF")
        pdf_path = _storage_dir(settings) / f"{report_id}.pdf"
        page_count, file_size = export_brief_report_pdf(doc, pdf_path, settings=settings)

        rel_path = str(Path(settings.brief_report_storage_dir) / f"{report_id}.pdf")
        await repo.mark_report_done(
            db,
            report_id=report_id,
            pdf_path=rel_path,
            doc_json=doc,
            page_count=page_count,
            file_size=file_size,
        )
        await db.commit()

        return BriefReportResponse(
            report_id=report_id,
            status="done",
            pdf_url=pdf_url(settings, report_id),
            pdf_page_count=page_count,
            pdf_file_size=file_size,
            toc=doc.get("toc"),
        )
    except BriefReportError:
        raise
    except Exception as exc:
        await repo.mark_report_failed(
            db,
            report_id=report_id,
            error_code="EXPORT_FAILED",
            error_message=str(exc)[:512],
        )
        await db.commit()
        raise BriefReportError("EXPORT_FAILED", f"报告生成失败：{exc}", 500) from exc


async def handle_brief_report(
    body: BriefReportRequest,
    ctx: UserContext,
    db: AsyncSession,
    settings: Settings | None = None,
) -> BriefReportResponse:
    return await _run_pipeline(body, ctx, db, settings or get_settings())


async def handle_brief_report_stream(
    body: BriefReportRequest,
    ctx: UserContext,
    db: AsyncSession,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    cfg = settings or get_settings()
    event_queue: asyncio.Queue[str | tuple[str, Any]] = asyncio.Queue()

    async def emit(event: str) -> None:
        await event_queue.put(event)

    async def run_pipeline() -> None:
        try:
            result = await _run_pipeline(body, ctx, db, cfg, emit=emit)
            await event_queue.put(("done", result))
        except BriefReportError as exc:
            await event_queue.put(("error", exc))
        except Exception as exc:
            await event_queue.put(("error", BriefReportError("INTERNAL_ERROR", str(exc), 500)))

    task = asyncio.create_task(run_pipeline())
    yield sse.status_event("开始生成报告", phase="start")
    try:
        while True:
            item = await event_queue.get()
            if isinstance(item, tuple):
                kind, payload = item
                if kind == "done":
                    result: BriefReportResponse = payload
                    yield sse.report_done_event(
                        result.report_id,
                        pdf_url=result.pdf_url or "",
                        page_count=result.pdf_page_count or 0,
                        file_size=result.pdf_file_size or 0,
                    )
                    break
                if kind == "error":
                    exc: BriefReportError = payload
                    yield sse.error_event(exc.code, exc.message)
                    break
            else:
                yield item
    finally:
        await task
