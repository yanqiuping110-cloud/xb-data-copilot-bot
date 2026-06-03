"""
编译 LangGraph 问数有向图（7 节点）。
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    apply_policy,
    execute_sql,
    format_answer,
    generate_sql,
    match_curated,
    normalize_question,
    retrieve_context,
    route_after_match,
    route_after_validate,
    validate_sql_node,
)
from app.agent.state import AskGraphState


def build_ask_graph():
    """构建并编译问数 StateGraph。"""
    graph = StateGraph(AskGraphState)

    graph.add_node("normalize_question", normalize_question)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("match_curated", match_curated)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("apply_policy", apply_policy)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("format_answer", format_answer)

    graph.add_edge(START, "normalize_question")
    graph.add_edge("normalize_question", "retrieve_context")
    graph.add_edge("retrieve_context", "match_curated")
    graph.add_conditional_edges(
        "match_curated",
        route_after_match,
        {
            "validate_sql": "validate_sql",
            "generate_sql": "generate_sql",
            "format_answer": "format_answer",
        },
    )
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_conditional_edges(
        "validate_sql",
        route_after_validate,
        {
            "apply_policy": "apply_policy",
            "format_answer": "format_answer",
        },
    )
    graph.add_edge("apply_policy", "execute_sql")
    graph.add_edge("execute_sql", "format_answer")
    graph.add_edge("format_answer", END)

    return graph.compile()


@lru_cache
def get_ask_graph():
    """进程内单例编译图。"""
    return build_ask_graph()
