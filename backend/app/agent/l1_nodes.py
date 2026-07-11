"""
L1 样例图节点：知识库召回 + LLM 精选。
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.context_builder import MergedRecallContext
from app.agent.nodes import _cfg, _span
from app.agent.state import AskGraphState
from app.ask.l1_select_llm import select_l1_examples_llm
from app.ask.l1_service import (
    append_l1_to_context,
    candidates_from_rows,
    is_l1_visible,
)
from app.meta.repository import MetaRepository
from app.retrieval.hybrid import HybridRetriever
from config.settings import Settings


async def recall_sql_examples_node(state: AskGraphState, config: RunnableConfig) -> dict:
    """知识库召回 L1 样例候选（Top-K）。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = (
        state.get("recall_question")
        or state.get("normalized_question")
        or state.get("question")
        or ""
    )
    keywords = state.get("keywords") or []

    retriever = HybridRetriever(c["copilot_session"], settings)
    try:
        recalled, recall_mode = await retriever.recall_sql_examples_only(question, keywords)
    finally:
        await retriever.close()

    repo = MetaRepository(c["copilot_session"])
    ids = [item.example_id for item in recalled]
    score_map = {item.example_id: item.score for item in recalled}
    rows = await repo.get_sql_examples_by_ids(ids)
    visible_rows = [r for r in rows if is_l1_visible(r, c["ctx"])]
    candidates = candidates_from_rows(visible_rows, scores=score_map)

    await _span(
        config,
        "do_recall_sql_examples",
        t0,
        "success" if candidates else "empty",
        {
            "count": len(candidates),
            "recall_mode": recall_mode,
            "items": [
                {
                    "id": ex.id,
                    "pattern": ex.question_pattern[:80],
                    "score": round(ex.recall_score, 4),
                }
                for ex in candidates[:10]
            ],
        },
    )
    return {
        "l1_candidates": [ex.to_dict() for ex in candidates],
        "l1_recall_mode": recall_mode,
    }


def _dicts_to_candidates(raw: list[dict] | None) -> list:
    from app.ask.l1_service import L1ExampleCandidate

    if not raw:
        return []
    out: list[L1ExampleCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            L1ExampleCandidate(
                id=int(item["id"]),
                question_pattern=str(item.get("question_pattern") or ""),
                sql_text=str(item.get("sql_text") or ""),
                description=item.get("description"),
                recall_score=float(item.get("recall_score") or 0.0),
                select_reason=item.get("select_reason"),
            )
        )
    return out


async def select_l1_examples_node(state: AskGraphState, config: RunnableConfig) -> dict:
    """LLM 结合 STAR 与上下文精选 L1 样例，并追加到 context_text。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("question") or ""
    recall_question = (
        state.get("recall_question")
        or state.get("normalized_question")
        or question
    )
    candidates = _dicts_to_candidates(state.get("l1_candidates"))
    merged: MergedRecallContext | None = state.get("merged_recall")
    context_text = state.get("context_text") or ""

    result = await select_l1_examples_llm(
        settings=settings,
        question=question,
        recall_question=recall_question,
        candidates=candidates,
        context_text=context_text,
        merged=merged,
        memory_star=state.get("memory_star"),
        reference_type=state.get("reference_type"),
        thinking_queue=c.get("thinking_delta_queue"),
    )

    selected = result.selected
    updated_context = append_l1_to_context(context_text, selected)
    status = "degraded" if result.fallback else "success"
    detail: dict[str, Any] = {
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "selected_ids": [ex.id for ex in selected],
        "llm_input": result.llm_input,
        "llm_output": result.llm_output_raw,
        "token_in": result.token_in,
        "token_out": result.token_out,
        "fallback": result.fallback,
        "fallback_reason": result.fallback_reason,
    }
    await _span(config, "select_l1_examples", t0, status, detail)

    return {
        "selected_l1_examples": [ex.to_dict() for ex in selected],
        "context_text": updated_context,
    }
