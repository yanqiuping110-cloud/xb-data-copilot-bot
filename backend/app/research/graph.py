"""Research 外层 LangGraph（Phase 2 · 编排骨架）。"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.research.nodes import normalize_request, route_after_section
from app.research.state import ResearchGraphState


@lru_cache
def get_research_graph():
    """
    编译 Research Graph。

    节点 `execute_pipeline` 委托 `runner.stream_research_report` 的实际逻辑；
    本图用于结构验收与后续扩展（分支/DAG）。
    """
    graph = StateGraph(ResearchGraphState)
    graph.add_node("normalize_request", normalize_request)
    graph.add_node("execute_pipeline", _execute_pipeline_node)
    graph.add_edge(START, "normalize_request")
    graph.add_edge("normalize_request", "execute_pipeline")
    graph.add_edge("execute_pipeline", END)
    return graph.compile()


def _execute_pipeline_node(state: ResearchGraphState) -> dict:
    """占位节点：实际 SSE/JSON 执行仍由 runner 负责。"""
    _ = state
    return {"status": "running"}
