"""封面 / 目录摘要 / 结尾 LLM 文案。"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_client import complete_messages
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


def _fallback_plan(turns: list[dict[str, Any]], user_prompt: str) -> dict[str, Any]:
    from app.brief_report.builder import (
        _default_cover_title,
        _default_date,
        _default_ending_message,
        _polish_chapter_title,
        _short_summary,
    )

    toc = []
    for i, t in enumerate(turns, start=1):
        q = t.get("question") or ""
        a = t.get("answer") or ""
        toc.append(
            {
                "index": i,
                "title": _polish_chapter_title(q, a, index=i),
                "summary": _short_summary(a),
            }
        )
    return {
        "cover": {
            "title": _default_cover_title(turns, user_prompt),
            "subtitle": "",
            "org": "",
            "date": _default_date(),
        },
        "toc": toc,
        "ending": {
            "headline": "感谢聆听",
            "message": _default_ending_message(),
        },
    }


def _normalize_plan(raw: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
    cover = raw.get("cover") if isinstance(raw.get("cover"), dict) else {}
    ending = raw.get("ending") if isinstance(raw.get("ending"), dict) else {}
    toc_raw = raw.get("toc") or []
    toc: list[dict[str, Any]] = []
    for i, turn in enumerate(turns, start=1):
        item: dict[str, Any] = {"index": i}
        if i - 1 < len(toc_raw) and isinstance(toc_raw[i - 1], dict):
            src = toc_raw[i - 1]
            item["title"] = (src.get("title") or "").strip()
            item["summary"] = (src.get("summary") or "").strip()
        if not item.get("title"):
            from app.brief_report.builder import _polish_chapter_title

            item["title"] = _polish_chapter_title(
                turn.get("question") or "",
                turn.get("answer") or "",
                index=i,
            )
        if not item.get("summary"):
            from app.brief_report.builder import _short_summary

            item["summary"] = _short_summary(turn.get("answer") or "")
        toc.append(item)
    return {
        "cover": {
            "title": (cover.get("title") or "").strip(),
            "subtitle": (cover.get("subtitle") or "").strip(),
            "org": (cover.get("org") or "").strip(),
            "date": (cover.get("date") or "").strip(),
        },
        "ending": {
            "headline": (ending.get("headline") or "感谢聆听").strip(),
            "message": (ending.get("message") or "").strip(),
        },
        "toc": toc,
    }


async def plan_brief_report_copy(
    *,
    user_prompt: str,
    turns: list[dict[str, Any]],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """LLM 生成封面/目录/结尾文案；失败时启发式降级。"""
    cfg = settings or get_settings()
    if not cfg.brief_report_llm_enabled:
        return _fallback_plan(turns, user_prompt)

    sections_text = []
    for i, t in enumerate(turns, start=1):
        q = (t.get("question") or "").strip()
        a = (t.get("answer") or "").strip()[:400]
        sections_text.append(f"【{i}】问：{q}\n答：{a}")

    system = (
        "你是政务/教育汇报材料撰写专家。根据用户报告提示词与各章节问答摘要，"
        "输出庄重、简洁的汇报文案 JSON。禁止编造原文未出现的数据与数字。"
        "toc 中 title 须为 8～18 字的专业汇报章节名（如「月度参与趋势分析」），"
        "禁止照抄用户原问句或出现「用图表展示」等口语。"
        "只输出 JSON，不要 markdown 说明。"
    )
    human = (
        f"用户报告提示词：{user_prompt}\n\n"
        f"章节材料：\n" + "\n\n".join(sections_text) + "\n\n"
        '输出 JSON：{"cover":{"title":"...","subtitle":"...","org":"...","date":"..."},'
        '"toc":[{"title":"专业章节名","summary":"40-80字摘要"}],'
        '"ending":{"headline":"感谢聆听","message":"2-4句展望结语"}}'
    )
    try:
        content, _, _, _ = await complete_messages(
            cfg,
            [SystemMessage(content=system), HumanMessage(content=human)],
        )
        raw = _extract_json(content)
        if not raw:
            return _fallback_plan(turns, user_prompt)
        return _normalize_plan(raw, turns)
    except Exception:
        return _fallback_plan(turns, user_prompt)
