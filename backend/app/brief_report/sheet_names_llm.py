"""Excel Sheet 名称 LLM 生成。"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_client import complete_messages
from app.brief_report.builder import _polish_chapter_title
from app.brief_report.export_excel import sanitize_sheet_name, unique_sheet_names
from config.settings import Settings, get_settings

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_json(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    block = _JSON_BLOCK_RE.search(stripped)
    candidate = block.group(1).strip() if block else stripped
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(candidate[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _fallback_sheet_names(turns: list[dict[str, Any]]) -> list[str]:
    names = []
    for i, turn in enumerate(turns, start=1):
        names.append(
            _polish_chapter_title(
                turn.get("question") or "",
                turn.get("answer") or "",
                index=i,
            )
        )
    return unique_sheet_names(names)


def _sample_rows_text(rows: list[list[Any]], *, limit: int = 2) -> str:
    if not rows:
        return "（无数据行）"
    lines = []
    for row in rows[:limit]:
        lines.append(", ".join(str(c) for c in row))
    return " | ".join(lines)


async def plan_excel_sheet_names(
    turns: list[dict[str, Any]],
    settings: Settings | None = None,
) -> list[str]:
    """根据表格上下文生成 Excel sheet 名；失败时启发式降级。"""
    cfg = settings or get_settings()
    if not turns:
        return []
    if not cfg.brief_report_llm_enabled:
        return _fallback_sheet_names(turns)

    sections = []
    for i, turn in enumerate(turns, start=1):
        q = (turn.get("question") or "").strip()
        cols = turn.get("columns") or []
        rows = turn.get("rows") or []
        sections.append(
            f"【{i}】问：{q}\n"
            f"列：{', '.join(str(c) for c in cols) or '（无）'}\n"
            f"样例：{_sample_rows_text(rows)}"
        )

    system = (
        "你是数据分析报表命名助手。根据每个问数记录的表格列名与样例数据，"
        "为 Excel 工作表生成简短中文名称（6～14 字），体现数据主题而非照抄原问句。"
        "禁止出现「用图表展示」等口语，禁止编造未出现的指标。"
        "只输出 JSON，不要 markdown 说明。"
    )
    human = (
        "章节材料：\n"
        + "\n\n".join(sections)
        + '\n\n输出 JSON：{"sheets":[{"index":1,"name":"专业表名"}]}'
    )
    try:
        content, _, _, _ = await complete_messages(
            cfg,
            [SystemMessage(content=system), HumanMessage(content=human)],
        )
        raw = _extract_json(content)
        if not raw:
            return _fallback_sheet_names(turns)
        sheets_raw = raw.get("sheets") or []
        by_index: dict[int, str] = {}
        for item in sheets_raw:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            name = sanitize_sheet_name((item.get("name") or "").strip())
            if isinstance(idx, int) and name:
                by_index[idx] = name

        names: list[str] = []
        for i, turn in enumerate(turns, start=1):
            name = by_index.get(i)
            if not name:
                name = _polish_chapter_title(
                    turn.get("question") or "",
                    turn.get("answer") or "",
                    index=i,
                )
            names.append(name)
        return unique_sheet_names(names)
    except Exception:
        return _fallback_sheet_names(turns)
