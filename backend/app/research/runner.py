"""深度分析报告编排与 SSE 流。"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.log_config import get_logger
from app.research import audit as research_audit
from app.research import cancel_registry
from app.research import repository as repo
from app.research.chart_png import render_chart_png
from app.research.export_pdf import export_report_pdf
from app.research.planner import build_research_plan
from app.research.planner_llm import build_research_plan_llm
from app.research.render_html import render_report_html
from app.research.sub_ask_runner import run_section_ask, stream_section_ask
from app.research.synthesizer import synthesize_report_document
from app.research.synthesizer_llm import enrich_report_document
from app.research import streaming as rs
from app.schemas.research import ResearchReportRequest, ResearchReportResponse, ResearchSectionResponse
from app.security.prompt_boundary import sanitize_recall_text
from config.settings import Settings


logger = get_logger("research.runner")


class ResearchError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _scope_summary(ctx: UserContext) -> str:
    role = ctx.role.value if hasattr(ctx.role, "value") else str(ctx.role)
    sch = getattr(ctx, "active_sch_id", None)
    if sch:
        return f"{role} · sch_id={sch}"
    return role


def _pdf_public_url(settings: Settings, report_id: str) -> str:
    prefix = (settings.research_pdf_url_prefix or "/api/v1/research/report").rstrip("/")
    return f"{prefix}/{report_id}/pdf"


def _storage_dir(settings: Settings) -> Path:
    root = Path(settings.research_storage_dir)
    if not root.is_absolute():
        from config.settings import ROOT_DIR

        root = ROOT_DIR / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _charts_dir(settings: Settings, report_id: str) -> Path:
    d = _storage_dir(settings) / report_id / "charts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _maybe_render_section_chart(
    settings: Settings,
    report_id: str,
    section_index: int,
    result: dict[str, Any],
) -> str | None:
    path = _charts_dir(settings, report_id) / f"section_{section_index}.png"
    rendered = render_chart_png(
        chart_spec=result.get("chart_spec"),
        columns=result.get("columns"),
        rows=result.get("rows"),
        output_path=path,
        title=result.get("title"),
    )
    if rendered:
        result["chart_png_path"] = str(path)
    return rendered


def _plan_from_user_sections(body: ResearchReportRequest, request_text: str) -> dict[str, Any]:
    sections = []
    for i, s in enumerate(body.sections or [], start=1):
        sections.append(
            {
                "index": i,
                "title": s.title,
                "question": s.question,
                "intent": s.intent or "open_query",
                "visualization": {"enabled": True, "preferred_types": ["line", "bar"]},
            }
        )
    title = request_text[:40] if len(request_text) <= 40 else request_text[:40].rstrip() + "…"
    return {
        "title": title or "深度洞察报告",
        "templateCode": "custom",
        "sections": sections,
        "synthesis_hints": ["突出关键变化", "给出可行动建议"],
    }


async def _load_branch_inherited(
    session: AsyncSession,
    *,
    parent_report_id: str,
    branch_from_section: int,
    user_id: int,
) -> list[dict[str, Any]]:
    parent = await repo.get_report(session, report_id=parent_report_id, user_id=user_id)
    if parent is None:
        raise ResearchError("PARENT_NOT_FOUND", "来源报告不存在", 404)
    rows = await repo.list_sections(session, report_id=parent_report_id)
    inherited: list[dict[str, Any]] = []
    fork = int(branch_from_section)
    for ps in rows:
        if int(ps["section_index"]) >= fork:
            continue
        inherited.append(
            {
                "section_index": ps["section_index"],
                "title": ps["title"],
                "question": ps.get("question") or ps["title"],
                "intent": ps.get("intent"),
                "status": ps["status"] if ps["status"] in ("success", "degraded") else "success",
                "answer": ps.get("answer"),
                "columns": None,
                "rows": None,
                "chart_spec": None,
                "sub_trace_id": ps.get("sub_trace_id"),
                "latency_ms": ps.get("latency_ms"),
            }
        )
    return inherited


async def _resolve_plan(
    body: ResearchReportRequest,
    ctx: UserContext,
    session: AsyncSession,
    settings: Settings,
    request_text: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (plan, sections_to_run, inherited_results)。"""
    inherited: list[dict[str, Any]] = []
    if body.parent_report_id and body.branch_from_section:
        inherited = await _load_branch_inherited(
            session,
            parent_report_id=body.parent_report_id,
            branch_from_section=int(body.branch_from_section),
            user_id=ctx.user_id,
        )

    if body.sections:
        plan = _plan_from_user_sections(body, request_text)
    else:
        plan = await build_research_plan_llm(
            request_text,
            template_code=body.template_code or "monthly_ops",
            max_sections=settings.research_max_sections,
            user_context={"role": _scope_summary(ctx)},
            settings=settings,
        )

    sections = list(plan.get("sections") or [])
    if inherited:
        fork = int(body.branch_from_section or 1)
        sections = [s for s in sections if int(s["index"]) >= fork]
        if not sections:
            parent_plan = plan
            tpl = build_research_plan(
                request_text,
                template_code=body.template_code or "monthly_ops",
                max_sections=settings.research_max_sections,
            )
            sections = [s for s in tpl.get("sections", []) if int(s["index"]) >= fork]
            plan = {**parent_plan, "sections": inherited + sections}
    return plan, sections, inherited


async def run_research_report(
    body: ResearchReportRequest,
    ctx: UserContext,
    session: AsyncSession,
    settings: Settings,
) -> ResearchReportResponse:
    """一次性 JSON 模式。"""
    final: ResearchReportResponse | None = None
    async for frame in stream_research_report(body, ctx, session, settings):
        if frame.startswith("event: report_done"):
            import json

            data_line = [ln for ln in frame.split("\n") if ln.startswith("data:")][0]
            payload = json.loads(data_line[5:].strip())
            final = ResearchReportResponse.model_validate(payload)
    if final is None:
        raise ResearchError("RESEARCH_FAILED", "报告未完成")
    return final


async def stream_research_report(
    body: ResearchReportRequest,
    ctx: UserContext,
    session: AsyncSession,
    settings: Settings,
) -> AsyncIterator[str]:
    """SSE 流式执行深度分析报告。"""
    if not settings.research_enabled:
        yield rs.error_event("RESEARCH_DISABLED", "深度洞察功能未启用")
        return

    t0 = time.perf_counter()
    report_id = f"rpt-{uuid.uuid4().hex[:16]}"
    request_text = (body.request_text or "").strip()
    if not request_text:
        yield rs.error_event("INVALID_REQUEST", "分析意图不能为空")
        return

    request_text, _ = sanitize_recall_text(
        request_text,
        enabled=settings.prompt_boundary_enabled,
    )

    running_n = await repo.count_running_reports(session, user_id=ctx.user_id)
    if running_n >= settings.research_max_concurrent_per_user:
        yield rs.error_event("TOO_MANY_RUNNING", "已有进行中的报告，请稍后再试")
        return

    template_code = body.template_code or "monthly_ops"
    try:
        plan, sections, inherited_results = await _resolve_plan(
            body, ctx, session, settings, request_text
        )
    except ResearchError as exc:
        yield rs.error_event(exc.code, exc.message)
        return

    title = plan.get("title") or "深度洞察报告"

    try:
        await repo.create_report(
            session,
            report_id=report_id,
            user_id=ctx.user_id,
            title=title,
            request_text=request_text,
            template_code=template_code,
            session_id=body.session_id,
            parent_report_id=body.parent_report_id,
            branch_from_section=body.branch_from_section,
        )
        all_sections_db: list[dict[str, Any]] = []
        for ir in inherited_results:
            all_sections_db.append(
                {
                    "index": int(ir["section_index"]),
                    "title": ir.get("title") or "",
                    "question": ir.get("question") or ir.get("title") or "",
                    "intent": ir.get("intent") or "open_query",
                }
            )
        all_sections_db.extend(sections)
        await repo.update_report_plan(
            session,
            report_id=report_id,
            plan=plan,
            section_total=len(all_sections_db),
        )
        await repo.insert_sections(session, report_id=report_id, sections=all_sections_db)
        for ir in inherited_results:
            await repo.update_section_result(
                session,
                report_id=report_id,
                section_index=int(ir["section_index"]),
                status=ir.get("status") or "success",
                answer=ir.get("answer"),
                sub_trace_id=ir.get("sub_trace_id"),
                latency_ms=ir.get("latency_ms"),
            )
        await research_audit.log_research_event(
            session,
            ctx=ctx,
            report_id=report_id,
            action="REPORT_CREATE",
            detail=request_text[:200],
        )
        await session.commit()
    except Exception as exc:
        logger.exception("创建报告失败 report_id=%s", report_id)
        yield rs.error_event("DB_ERROR", f"创建报告失败: {exc}")
        return

    cancel_registry.clear_cancel(report_id)
    last_heartbeat = time.perf_counter()

    yield rs.report_started_event(report_id, title)
    yield rs.status_event("正在理解您的分析意图…", phase="planning")

    plan_payload = [
        {"index": s["index"], "title": s["title"], "intent": s.get("intent") or "open_query"}
        for s in sections
    ]
    for ir in inherited_results:
        yield rs.plan_item_event(
            int(ir["section_index"]),
            ir.get("title") or "",
            ir.get("intent") or "open_query",
        )
        yield rs.activity_event("info", f"继承章节：{ir.get('title')}")
    for s in sections:
        await asyncio.sleep(0.05 if settings.research_demo_pace == "demo" else 0)
        yield rs.plan_item_event(s["index"], s["title"], s.get("intent") or "open_query")
        yield rs.activity_event("info", f"已规划任务：{s['title']}")
    yield rs.plan_revealed_event(plan_payload)

    yield rs.status_event(f"已规划 {len(sections)} 个分析章节，开始执行…", phase="section_running")

    section_results: list[dict[str, Any]] = list(inherited_results)
    use_stream = bool(body.options and body.options.stream)

    for s in sections:
        if cancel_registry.is_cancelled(report_id):
            await repo.mark_report_cancelled(session, report_id=report_id)
            await session.commit()
            cancel_registry.clear_cancel(report_id)
            yield rs.error_event("CANCELLED", "报告已取消")
            return

        if _elapsed_ms(t0) > settings.research_total_timeout_sec * 1000:
            yield rs.error_event("TOTAL_TIMEOUT", "报告总耗时超限")
            break

        idx = int(s["index"])
        yield rs.section_start_event(idx, s["title"], s["question"])
        yield rs.section_progress_event(idx, pipeline_step=1, label="理解问题")
        yield rs.activity_event("info", f"▸ 第{idx}节 · {s['title']} · 开始")

        result: dict[str, Any] | None = None

        async def _stream_section() -> AsyncIterator[str]:
            nonlocal result, last_heartbeat
            async for evt in stream_section_ask(
                question=s["question"],
                ctx=ctx,
                copilot_session=session,
                settings=settings,
                session_id=body.session_id,
                parent_report_id=report_id,
                section_index=idx,
            ):
                if evt["type"] == "progress":
                    yield rs.section_progress_event(
                        idx,
                        pipeline_step=evt["pipeline_step"],
                        label=evt["label"],
                        tool=evt.get("tool"),
                    )
                    yield rs.activity_event("info", f"  {evt['label']}")
                    last_heartbeat = time.perf_counter()
                elif evt["type"] == "text_delta":
                    yield rs.text_delta_event("section", evt["delta"], section_index=idx)
                elif evt["type"] == "preview":
                    yield rs.section_preview_event(idx, evt["columns"], evt["rows_sample"])
                elif evt["type"] == "chart":
                    yield rs.chart_ready_event(idx, evt["chart_spec"])
                elif evt["type"] == "done":
                    result = evt["result"]

        try:
            if use_stream:
                async for frame in _stream_section():
                    yield frame
                    if time.perf_counter() - last_heartbeat >= settings.research_heartbeat_interval_sec:
                        yield rs.heartbeat_event(_elapsed_ms(t0))
                        last_heartbeat = time.perf_counter()
            else:
                result = await asyncio.wait_for(
                    run_section_ask(
                        question=s["question"],
                        ctx=ctx,
                        copilot_session=session,
                        settings=settings,
                        session_id=body.session_id,
                        parent_report_id=report_id,
                        section_index=idx,
                    ),
                    timeout=settings.research_section_timeout_sec,
                )
        except asyncio.TimeoutError:
            result = {
                "section_index": idx,
                "status": "fail",
                "answer": None,
                "error_code": "SECTION_TIMEOUT",
                "latency_ms": settings.research_section_timeout_sec * 1000,
            }
            yield rs.activity_event("warn", f"第{idx}节超时")

        if result is None:
            result = {
                "section_index": idx,
                "status": "fail",
                "error_code": "SECTION_NO_RESULT",
            }
        result["title"] = s["title"]
        result["question"] = s["question"]
        result["intent"] = s.get("intent")
        _maybe_render_section_chart(settings, report_id, idx, result)
        section_results.append(result)

        if not use_stream and result.get("answer") and settings.research_stream_text_delta:
            ans = result.get("answer") or ""
            for i in range(0, len(ans), 40):
                yield rs.text_delta_event("section", ans[i : i + 40], section_index=idx)

        await repo.update_section_result(
            session,
            report_id=report_id,
            section_index=idx,
            status=result.get("status") or "fail",
            answer=result.get("answer"),
            columns=result.get("columns"),
            rows=result.get("rows"),
            chart_spec=result.get("chart_spec"),
            sub_trace_id=result.get("sub_trace_id"),
            error_code=result.get("error_code"),
            latency_ms=result.get("latency_ms"),
        )
        await session.commit()

        yield rs.section_done_event(
            idx,
            status=result.get("status") or "fail",
            sub_trace_id=result.get("sub_trace_id"),
            latency_ms=result.get("latency_ms"),
            answer=result.get("answer"),
        )
        yield rs.activity_event(
            "success" if result.get("status") == "success" else "warn",
            f"{'✓' if result.get('status') == 'success' else '✗'} 第{idx}节完成",
        )
        yield rs.heartbeat_event(_elapsed_ms(t0))

    cancel_registry.clear_cancel(report_id)

    if not section_results:
        yield rs.error_event("RESEARCH_FAILED", "无章节结果")
        return

    yield rs.status_event("正在汇总洞察与排版 PDF…", phase="synthesizing")
    scope = _scope_summary(ctx)
    doc = synthesize_report_document(
        report_id=report_id,
        plan=plan,
        section_results=section_results,
        scope_summary=scope,
        theme_name=settings.research_pdf_theme,
    )
    doc = await enrich_report_document(
        doc,
        plan=plan,
        section_results=section_results,
        scope_summary=scope,
        settings=settings,
    )

    exec_summary = "\n".join(doc.get("executiveSummary", {}).get("paragraphs") or [])
    if settings.research_stream_text_delta and exec_summary:
        chunk = 40
        for i in range(0, len(exec_summary), chunk):
            yield rs.text_delta_event("summary", exec_summary[i : i + chunk])

    yield rs.insights_ready_event(
        exec_summary,
        doc.get("findings") or [],
        doc.get("recommendations") or [],
    )
    rec_text = "\n".join(f"• {r}" for r in (doc.get("recommendations") or [])[:6])
    if settings.research_stream_text_delta and rec_text:
        yield rs.text_delta_event("recommendation", f"\n\n{rec_text}")

    yield rs.status_event("正在生成 PDF 长报告…", phase="exporting")
    pdf_path = _storage_dir(settings) / f"{report_id}.pdf"
    if settings.research_keep_html_debug:
        html_path = _storage_dir(settings) / f"{report_id}.html"
        html_path.write_text(render_report_html(doc), encoding="utf-8")

    page_count, file_size = export_report_pdf(doc, pdf_path, settings=settings)
    pdf_url = _pdf_public_url(settings, report_id)

    success_n = sum(1 for r in section_results if r.get("status") == "success")
    final_status = "success" if success_n == len(section_results) else ("partial" if success_n else "fail")
    latency_ms = _elapsed_ms(t0)
    total_sections = len(section_results)

    await repo.finish_report(
        session,
        report_id=report_id,
        status=final_status,
        report_doc=doc,
        pdf_path=str(pdf_path),
        pdf_url=pdf_url,
        pdf_page_count=page_count,
        pdf_file_size=file_size,
        latency_ms=latency_ms,
        error_code=None if success_n else "PARTIAL_SECTIONS",
        error_message=None if success_n == len(section_results) else f"成功 {success_n}/{len(section_results)} 节",
    )
    await session.commit()

    response = _build_response(
        report_id=report_id,
        title=title,
        status=final_status,
        section_total=total_sections,
        section_done=success_n,
        pdf_url=pdf_url,
        pdf_page_count=page_count,
        pdf_file_size=file_size,
        latency_ms=latency_ms,
        section_results=section_results,
        doc=doc,
    )
    yield rs.pdf_ready_event(pdf_url, page_count, file_size)
    yield rs.report_done_event(response.model_dump(by_alias=True, mode="json"))


async def get_report_detail(
    session: AsyncSession,
    *,
    report_id: str,
    user_id: int,
) -> ResearchReportResponse | None:
    row = await repo.get_report(session, report_id=report_id, user_id=user_id)
    if not row:
        return None
    sections = await repo.list_sections(session, report_id=report_id)
    doc = row.get("report_doc_json")
    if isinstance(doc, str):
        import json

        doc = json.loads(doc)
    insights = (doc or {}).get("findings") if doc else None
    exec_sum = None
    if doc:
        exec_sum = "\n".join((doc.get("executiveSummary") or {}).get("paragraphs") or [])
    section_results = [
        {
            "section_index": s["section_index"],
            "title": s["title"],
            "question": s.get("question") or s["title"],
            "intent": s.get("intent"),
            "status": s["status"],
            "answer": s.get("answer"),
            "sub_trace_id": s.get("sub_trace_id"),
            "latency_ms": s.get("latency_ms"),
            "error_code": s.get("error_code"),
        }
        for s in sections
    ]
    return _build_response(
        report_id=row["report_id"],
        title=row["title"],
        status=row["status"],
        section_total=int(row.get("section_total") or 0),
        section_done=int(row.get("section_done") or 0),
        pdf_url=row.get("report_pdf_url"),
        pdf_page_count=row.get("pdf_page_count"),
        pdf_file_size=row.get("pdf_file_size"),
        latency_ms=row.get("latency_ms_total"),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        section_results=section_results,
        doc=doc,
        insights=insights,
        executive_summary=exec_sum,
    )


def _build_response(
    *,
    report_id: str,
    title: str,
    status: str,
    section_total: int,
    section_done: int,
    pdf_url: str | None,
    pdf_page_count: int | None,
    pdf_file_size: int | None,
    latency_ms: int | None,
    section_results: list[dict[str, Any]],
    doc: dict[str, Any] | None = None,
    insights: list[dict[str, Any]] | None = None,
    executive_summary: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> ResearchReportResponse:
    secs = [
        ResearchSectionResponse(
            section_index=int(s.get("section_index") or 0),
            title=s.get("title") or "",
            question=s.get("question") or s.get("title") or "",
            intent=s.get("intent"),
            status=s.get("status") or "fail",
            answer=s.get("answer"),
            sub_trace_id=s.get("sub_trace_id"),
            latency_ms=s.get("latency_ms"),
            error_code=s.get("error_code"),
        )
        for s in section_results
    ]
    if executive_summary is None and doc:
        executive_summary = "\n".join((doc.get("executiveSummary") or {}).get("paragraphs") or [])
    if insights is None and doc:
        insights = doc.get("findings")
    return ResearchReportResponse(
        report_id=report_id,
        status=status,
        title=title,
        section_total=section_total,
        section_done=section_done,
        pdf_url=pdf_url,
        pdf_page_count=pdf_page_count,
        pdf_file_size=pdf_file_size,
        latency_ms=latency_ms,
        error_code=error_code,
        error_message=error_message,
        sections=secs,
        insights=insights,
        executive_summary=executive_summary,
    )


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def resolve_pdf_path(settings: Settings, report_id: str) -> Path | None:
    path = _storage_dir(settings) / f"{report_id}.pdf"
    return path if path.is_file() else None
