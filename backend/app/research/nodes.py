"""Research LangGraph 节点（Phase 2）。"""

from __future__ import annotations

from typing import Any

from app.research.state import ResearchGraphState


def route_after_section(state: ResearchGraphState) -> str:
    plan = state.get("plan") or {}
    sections = plan.get("sections") or []
    idx = int(state.get("section_index") or 0)
    if idx < len(sections):
        return "execute_section"
    return "synthesize_report"


def normalize_request(state: ResearchGraphState) -> dict[str, Any]:
    text = (state.get("request_text") or "").strip()
    return {"request_text": text[:2000]}


def mark_section_index(state: ResearchGraphState) -> dict[str, Any]:
    return {"section_index": int(state.get("section_index") or 0) + 1}


def bump_section_after_run(state: ResearchGraphState) -> dict[str, Any]:
    return {"section_index": int(state.get("section_index") or 0) + 1}
