"""Research Planner（LLM 路径 + 启发式降级）。"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_sql import build_llm
from app.research.planner import build_research_plan, _title_from_request
from config.settings import Settings

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

_BLACKLIST = ("删除", "drop ", "truncate", "导出全表", "insert ", "update ")


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


def _normalize_llm_plan(raw: dict[str, Any], *, request_text: str, max_sections: int) -> dict[str, Any]:
    sections_raw = raw.get("sections") or []
    sections: list[dict[str, Any]] = []
    for i, s in enumerate(sections_raw[:max_sections], start=1):
        if not isinstance(s, dict):
            continue
        question = (s.get("question") or s.get("title") or "").strip()
        if len(question) < 4:
            continue
        if any(b in question.lower() for b in _BLACKLIST):
            continue
        sections.append(
            {
                "index": i,
                "title": (s.get("title") or question)[:64],
                "question": question,
                "intent": s.get("intent") or "open_query",
                "visualization": s.get("visualization") or {"enabled": True, "preferred_types": ["line", "bar"]},
            }
        )
    if not sections:
        raise ValueError("LLM plan has no valid sections")
    return {
        "title": raw.get("title") or _title_from_request(request_text),
        "templateCode": "custom",
        "sections": sections,
        "synthesis_hints": raw.get("synthesis_hints") or ["突出关键变化", "给出可行动建议"],
    }


async def build_research_plan_llm(
    request_text: str,
    *,
    template_code: str | None = None,
    max_sections: int = 12,
    user_context: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """LLM 分解分析任务；失败时降级启发式模板。"""
    from config.settings import get_settings

    settings = settings or get_settings()
    code = (template_code or "monthly_ops").strip() or "monthly_ops"

    if not settings.research_llm_planner_enabled or code != "custom":
        return build_research_plan(
            request_text,
            template_code=code,
            max_sections=max_sections,
        )

    scope = (user_context or {}).get("role") or "USER"
    system = (
        "你是企业数据分析任务规划助手。将用户分析意图拆解为可独立问数的章节列表。"
        "只输出 JSON，不要 markdown 说明。每节 question 必须是完整自然语言问句，"
        "禁止「见上一节」指代，禁止写库/删库/导出全表。"
        f"章节数不超过 {max_sections}。"
    )
    human = (
        f"用户角色/范围：{scope}\n"
        f"分析意图：{request_text}\n\n"
        '输出 JSON：{"title":"...","sections":[{"title":"...","question":"...","intent":"trend|compare|rank|share|anomaly|open_query"}]}'
    )
    try:
        llm = build_llm(settings)
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        content = resp.content if hasattr(resp, "content") else str(resp)
        parsed = _extract_json(content)
        if parsed:
            return _normalize_llm_plan(parsed, request_text=request_text, max_sections=max_sections)
    except Exception:
        pass

    return build_research_plan(request_text, template_code=code, max_sections=max_sections)
