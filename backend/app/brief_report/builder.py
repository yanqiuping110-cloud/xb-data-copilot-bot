"""BriefReportDocument 组装。"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.brief_report.backgrounds import default_backgrounds, resolve_background_path
from app.brief_report.chart_resolver import resolve_chart_png
from app.brief_report.theme import load_theme
from app.brief_report.turn_quality import is_empty_answer
from config.settings import Settings, get_settings


def _short_title(question: str, *, max_len: int = 32) -> str:
    q = (question or "").strip()
    if len(q) <= max_len:
        return q
    return q[: max_len - 1] + "…"


def _polish_chapter_title(question: str, answer: str, *, index: int) -> str:
    """无 LLM 时将问句提炼为汇报型短标题。"""
    q = (question or "").strip()
    for prefix in ("用图表展示", "用折线图展示", "用饼状图展示", "用柱状图展示", "请帮我", "请", "帮我"):
        if q.startswith(prefix):
            q = q[len(prefix) :].strip()
    q = re.sub(r"[，,]?用\S{1,6}图展示.*$", "", q).strip(" ，,。.")
    if len(q) >= 6:
        return _short_title(q, max_len=22)
    if answer and len(answer) > 12:
        return _short_title(answer, max_len=22)
    return f"第{index}节 数据分析洞察"


def _toc_code(index: int) -> str:
    return f"{index:02d}"


def _truncate_table(
    columns: list[str],
    rows: list[list[Any]],
    *,
    max_rows: int,
) -> dict[str, Any]:
    total = len(rows)
    shown = rows[:max_rows]
    return {
        "columns": columns,
        "rows": shown,
        "truncated": total > max_rows,
        "totalRows": total,
    }


def build_brief_report_document(
    *,
    session_id: str,
    user_prompt: str,
    turns: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
    llm_plan: dict[str, Any] | None = None,
    work_dir: Path | None = None,
    settings: Settings | None = None,
    progress_cb: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    """将 turn 快照与 LLM 文案组装为 BriefReportDocument。"""
    cfg = settings or get_settings()
    opts = options or {}
    theme_name = (opts.get("theme") or cfg.brief_report_theme or "presentation").strip()
    theme = load_theme(theme_name)

    cover_bg = opts.get("cover_background") or opts.get("coverBackground")
    ending_bg = opts.get("ending_background") or opts.get("endingBackground")
    default_cover, default_ending = default_backgrounds(theme, settings=cfg)
    cover_bg = cover_bg or default_cover
    ending_bg = ending_bg or default_ending

    report_id = f"brpt-{uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()
    plan = llm_plan or {}

    cover_plan = plan.get("cover") or {}
    ending_plan = plan.get("ending") or {}
    toc_plan = plan.get("toc") or []

    cover = {
        "background": cover_bg,
        "backgroundPath": str(resolve_background_path(cover_bg, settings=cfg) or ""),
        "title": opts.get("title") or cover_plan.get("title") or _default_cover_title(turns, user_prompt),
        "subtitle": opts.get("subtitle") or cover_plan.get("subtitle") or "",
        "org": opts.get("org") or cover_plan.get("org") or "",
        "date": opts.get("report_date") or opts.get("reportDate") or cover_plan.get("date") or _default_date(),
    }
    ending = {
        "background": ending_bg,
        "backgroundPath": str(resolve_background_path(ending_bg, settings=cfg) or ""),
        "headline": ending_plan.get("headline") or "感谢聆听",
        "message": opts.get("ending_message") or opts.get("endingMessage") or ending_plan.get("message") or _default_ending_message(),
    }

    charts_dir = (work_dir or cfg.brief_report_storage_path) / report_id / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    chapters: list[dict[str, Any]] = []
    toc: list[dict[str, Any]] = []
    max_rows = cfg.brief_report_table_max_rows
    total = len(turns)

    if progress_cb:
        progress_cb("组装报告结构", 34)

    for i, turn in enumerate(turns, start=1):
        toc_item = _toc_item_for_index(toc_plan, i)
        title = toc_item.get("title") or _polish_chapter_title(
            turn.get("question") or "",
            turn.get("answer") or "",
            index=i,
        )
        summary = toc_item.get("summary") or _short_summary(turn.get("answer") or "")

        answer_text = turn.get("answer") or ""
        if is_empty_answer(answer_text):
            answer_text = ""

        if progress_cb and total:
            pct = 36 + int((i - 1) / total * 38)
            progress_cb(f"渲染第 {i}/{total} 章图表", pct)

        chart_path = None
        if work_dir is not None:
            chart_path = resolve_chart_png(
                trace_id=turn["trace_id"],
                chart_spec=turn.get("chart_spec"),
                columns=turn.get("columns"),
                rows=turn.get("rows"),
                title=title,
                work_dir=charts_dir,
                settings=cfg,
            )

        table = None
        cols = turn.get("columns") or []
        rows = turn.get("rows") or []
        if cols and rows:
            table = _truncate_table(cols, rows, max_rows=max_rows)

        chapter: dict[str, Any] = {
            "index": i,
            "traceId": turn["trace_id"],
            "title": title,
            "question": turn.get("question") or "",
            "answer": answer_text,
            "chartPngPath": chart_path,
            "table": table,
        }
        if opts.get("include_sql_appendix") or opts.get("includeSqlAppendix"):
            chapter["sql"] = turn.get("final_sql")

        chapters.append(chapter)
        toc.append(
            {
                "index": i,
                "code": _toc_code(i),
                "title": title,
                "summary": summary,
            }
        )
        if progress_cb and total:
            pct = 36 + int(i / total * 38)
            progress_cb(f"已完成第 {i}/{total} 章", pct)

    if progress_cb:
        progress_cb("报告内容组装完成", 76)

    return {
        "meta": {
            "reportId": report_id,
            "sessionId": session_id,
            "generatedAt": now,
            "userPrompt": user_prompt,
            "theme": theme_name,
            "pageLayout": opts.get("page_layout") or opts.get("pageLayout") or cfg.brief_report_page_layout,
        },
        "theme": theme,
        "cover": cover,
        "toc": toc,
        "chapters": chapters,
        "ending": ending,
    }


def _toc_item_for_index(toc_plan: list[Any], index: int) -> dict[str, Any]:
    for item in toc_plan:
        if isinstance(item, dict) and item.get("index") == index:
            return item
    if 0 <= index - 1 < len(toc_plan) and isinstance(toc_plan[index - 1], dict):
        return toc_plan[index - 1]
    return {}


def _default_cover_title(turns: list[dict[str, Any]], user_prompt: str) -> str:
    if user_prompt and len(user_prompt.strip()) >= 4:
        return user_prompt.strip()[:48]
    if turns:
        return _short_title(turns[0].get("question") or "数据分析汇报", max_len=48)
    return "数据分析汇报"


def _default_date() -> str:
    now = datetime.now()
    return f"{now.year}年{now.month}月"


def _default_ending_message() -> str:
    return "期待数据洞察为教育事业注入新活力，助力科学决策与高质量发展。"


def _short_summary(answer: str, *, max_len: int = 72) -> str:
    text = re.sub(r"\s+", " ", (answer or "").strip())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
