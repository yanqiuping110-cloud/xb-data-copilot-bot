"""
Agent Memory LangGraph 节点：会话槽位、用户偏好、LLM STAR 记忆上下文处理。
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.nodes import _span
from app.agent.state import AskGraphState
from app.memory.memory_llm import process_memory_context_llm
from app.memory.memory_service import MemoryService
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


async def process_memory_context_node(state: AskGraphState, config: RunnableConfig) -> dict:
    """LLM STAR 记忆上下文：解析问句、决定注入内容，供召回/plan/SQL 使用。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or state.get("question") or ""
    memory = state.get("session_memory")

    result = await process_memory_context_llm(
        settings=settings,
        question=question,
        memory=memory,
        preferences=state.get("user_preferences") or [],
        thinking_queue=c.get("thinking_delta_queue"),
    )

    status = "degraded" if result.fallback else "success"
    detail = {
        "llm_input": result.llm_input,
        "llm_output": result.llm_output_raw,
        "star": result.star,
        "reference_type": result.reference_type,
        "inject": result.inject,
        "inherit": result.inherit,
        "resolved_question": result.resolved_question,
        "recall_question": result.recall_question,
        "memory_prompt_text": result.memory_prompt_text,
        "memory_chars": len(result.memory_prompt_text or ""),
        "token_in": result.token_in,
        "token_out": result.token_out,
        "fallback": result.fallback,
        "fallback_reason": result.fallback_reason,
    }
    await _span(config, "process_memory_context", t0, status, detail)

    out: dict[str, Any] = {
        "memory_prompt_text": result.memory_prompt_text,
        "memory_star": result.star,
        "reference_type": result.reference_type,
        "reference_hint": result.star.get("action"),
    }
    if result.resolved_question and result.resolved_question != question:
        out["normalized_question"] = result.resolved_question
    if result.recall_question:
        out["recall_question"] = result.recall_question
    return out


# 兼容旧图名 / 测试引用
resolve_references_node = process_memory_context_node
