"""
Agent Memory LangGraph 节点：会话槽位、用户偏好、指代消解。
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.nodes import _span
from app.agent.state import AskGraphState
from app.memory.memory_service import MemoryService, build_memory_prompt_sections
from app.memory.reference_resolver import resolve_references
from config.settings import Settings


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


async def load_session_memory(state: AskGraphState, config: RunnableConfig) -> dict:
    """按 session_id 加载 L1 会话短期记忆（Fail-open）。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    session_id = c.get("session_id")
    ctx = c["ctx"]

    svc = MemoryService(c["copilot_session"], settings)
    memory = await svc.load_session_memory(session_id, ctx.user_id)

    detail = {
        "session_id": session_id,
        "turn_count": len(memory.turns),
        "memory_skipped": memory.skipped,
        "skip_reason": memory.skip_reason,
    }
    status = "success" if not memory.skipped else "degraded"
    await _span(config, "load_session_memory", t0, status, detail)

    return {
        "session_memory": memory,
        "memory_skipped": memory.skipped,
    }


async def load_user_preference(state: AskGraphState, config: RunnableConfig) -> dict:
    """加载 L2 用户显式偏好（Fail-open）。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    ctx = c["ctx"]

    svc = MemoryService(c["copilot_session"], settings)
    prefs = await svc.load_user_preferences(ctx.user_id)

    detail = {"count": len(prefs), "keys": [p.pref_key for p in prefs]}
    await _span(config, "load_user_preference", t0, "success", detail)

    return {"user_preferences": prefs}


async def resolve_references_node(state: AskGraphState, config: RunnableConfig) -> dict:
    """P1 轻量指代消解：失败则原问句不变。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or state.get("question") or ""
    memory = state.get("session_memory")

    resolved, hint, matched = resolve_references(question, memory)

    # 拼装 memory prompt（在 build_llm_context / generate_sql 之前注入）
    memory_text, mem_detail = build_memory_prompt_sections(
        memory,
        state.get("user_preferences") or [],
        max_chars=settings.memory_prompt_max_chars,
        inject_session=settings.session_memory_enabled,
        boundary_enabled=settings.prompt_boundary_enabled,
    )
    if hint:
        memory_text = (memory_text + "\n【指代消解提示】\n" + hint).strip()

    detail = {
        "reference_matched": matched,
        "memory_chars": mem_detail.get("chars", 0),
        "session_injected": mem_detail.get("session_injected"),
        "preference_count": mem_detail.get("preference_count", 0),
        "truncated": mem_detail.get("truncated", False),
    }
    await _span(config, "resolve_references", t0, "success" if matched else "fail", detail)

    result: dict[str, Any] = {
        "memory_prompt_text": memory_text,
        "reference_hint": hint,
    }
    if matched and resolved != question:
        result["normalized_question"] = resolved
    return result
