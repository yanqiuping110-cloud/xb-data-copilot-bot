"""
编译 LangGraph 问数有向图（多阶段召回 + L1 快路径 + correct_sql）。
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    apply_policy,
    correct_sql,
    execute_sql,
    format_answer,
    generate_sql,
    match_curated,
    normalize_question,
    route_after_execute,
    route_after_match,
    route_after_validate,
    validate_sql_node,
)
from app.agent.recall_nodes import (
    build_llm_context,
    extract_keywords_node,
    filter_metrics_node,
    filter_tables_node,
    merge_retrieved_info_node,
    recall_columns,
    recall_field_values,
    recall_metrics,
)
from app.agent.state import AskGraphState


def build_ask_graph():
    """构建并编译问数 StateGraph。"""
    graph = StateGraph(AskGraphState)

    graph.add_node("normalize_question", normalize_question)
    graph.add_node("extract_keywords", extract_keywords_node)
    # 节点名不可与 AskGraphState 字段同名（LangGraph 会报 state key 冲突）
    graph.add_node("do_recall_columns", recall_columns)
    graph.add_node("do_recall_metrics", recall_metrics)
    graph.add_node("do_recall_field_values", recall_field_values)
    graph.add_node("merge_retrieved_info", merge_retrieved_info_node)
    graph.add_node("filter_tables", filter_tables_node)
    graph.add_node("filter_metrics", filter_metrics_node)
    graph.add_node("build_llm_context", build_llm_context)
    graph.add_node("match_curated", match_curated)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("correct_sql", correct_sql)
    graph.add_node("apply_policy", apply_policy)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("format_answer", format_answer)

    graph.add_edge(START, "normalize_question")
    graph.add_edge("normalize_question", "extract_keywords")
    graph.add_edge("extract_keywords", "do_recall_columns")
    graph.add_edge("do_recall_columns", "do_recall_metrics")
    graph.add_edge("do_recall_metrics", "do_recall_field_values")
    graph.add_edge("do_recall_field_values", "merge_retrieved_info")
    graph.add_edge("merge_retrieved_info", "filter_tables")
    graph.add_edge("filter_tables", "filter_metrics")
    graph.add_edge("filter_metrics", "build_llm_context")
    graph.add_edge("build_llm_context", "match_curated")
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
            "correct_sql": "correct_sql",
            "format_answer": "format_answer",
        },
    )
    graph.add_edge("correct_sql", "validate_sql")
    graph.add_edge("apply_policy", "execute_sql")
    graph.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        {
            "correct_sql": "correct_sql",
            "format_answer": "format_answer",
        },
    )
    graph.add_edge("format_answer", END)

    return graph.compile()


@lru_cache
def get_ask_graph():
    """进程内单例编译图。"""
    return build_ask_graph()


def clear_ask_graph_cache() -> None:
    """图结构变更后清缓存（测试用）。"""
    get_ask_graph.cache_clear()
