"""
图表规格生成节点 build_chart。
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.chart_builder import build_chart_spec, infer_visualization_from_question, normalize_visualization_intent
from app.agent.nodes import _span
from app.agent.state import AskGraphState
from app.ask.column_labels import localize_result_columns
from app.schemas.chart import ChartSpec


def _visualization_intent_from_state(state: AskGraphState) -> dict[str, Any]:
    if state.get("visualization_intent"):
        return normalize_visualization_intent(state["visualization_intent"])
    plan = state.get("plan") or {}
    vis = plan.get("visualization")
    if vis:
        return normalize_visualization_intent(vis)
    question = state.get("normalized_question") or state.get("question") or ""
    return infer_visualization_from_question(question)


def _chart_spec_to_state(spec: ChartSpec) -> dict[str, Any]:
    return spec.model_dump(by_alias=False)


async def build_chart(state: AskGraphState, config: RunnableConfig) -> dict:
    """SQL 结果就绪后生成 chart_spec（不可图表时不影响问数成功）。"""
    t0 = time.perf_counter()
    error_code = state.get("error_code")
    rows = state.get("rows") or []

    if error_code and not rows:
        skipped = ChartSpec(chart_type="none", status="skipped", reject_reason="查询未成功或无数据")
        await _span(config, "build_chart", t0, "empty", {"status": "skipped"})
        return {
            "chart_spec": _chart_spec_to_state(skipped),
            "visualization_intent": _visualization_intent_from_state(state),
        }

    question = state.get("normalized_question") or state.get("question") or ""
    display_columns = localize_result_columns(
        state.get("columns"),
        question=question,
        state=state,
    )
    intent = _visualization_intent_from_state(state)
    spec = build_chart_spec(
        columns=display_columns,
        rows=rows,
        visualization_intent=intent,
        question=question,
        assembly_mode=state.get("assembly_mode"),
    )

    await _span(
        config,
        "build_chart",
        t0,
        "success" if spec.status == "ready" else "degraded",
        {
            "chart_type": spec.chart_type,
            "status": spec.status,
            "reject_reason": spec.reject_reason,
        },
    )
    return {
        "chart_spec": _chart_spec_to_state(spec),
        "visualization_intent": intent,
    }
