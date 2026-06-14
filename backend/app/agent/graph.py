"""
编译 LangGraph 问数有向图（多阶段召回 + Agent Loop + 分步 SQL + correct_sql）。
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.memory_nodes import (
    load_session_memory,
    load_user_preference,
    resolve_references_node,
)
from app.agent.nodes import (
    apply_policy,
    correct_sql,
    execute_sql,
    format_answer,
    generate_sql,
    normalize_question,
    route_after_execute,
    route_after_validate,
    validate_sql_node,
)
from app.agent.plan_nodes import plan_question, route_after_plan
from app.agent.agent_nodes import (
    agent_loop,
    build_agent_context,
    generate_sql_step,
    route_after_agent_loop,
)
from app.agent.sql_step_nodes import (
    assemble_result,
    execute_plan_sql_step,
    route_after_assemble_result,
    route_after_build_agent_context,
    route_after_execute_plan_sql_step,
)
from app.agent.verify_nodes import route_after_verify, verify_answer
from app.agent.recall_nodes import (
    build_llm_context,
    extract_keywords_node,
    filter_columns_node,
    filter_metrics_node,
    filter_tables_node,
    merge_retrieved_info_node,
    recall_field_values,
    recall_metrics,
    recall_tables,
)
from config.settings import get_settings
from app.agent.state import AskGraphState


def build_ask_graph(*, recall_columns_enabled: bool | None = None):
    """构建并编译问数 StateGraph。"""
    if recall_columns_enabled is None:
        recall_columns_enabled = get_settings().recall_columns_enabled

    graph = StateGraph(AskGraphState)

    graph.add_node("normalize_question", normalize_question)
    graph.add_node("load_session_memory", load_session_memory)
    graph.add_node("load_user_preference", load_user_preference)
    graph.add_node("resolve_references", resolve_references_node)
    graph.add_node("extract_keywords", extract_keywords_node)
    graph.add_node("do_recall_tables", recall_tables)
    if recall_columns_enabled:
        from app.agent.recall_nodes import recall_columns

        graph.add_node("do_recall_columns", recall_columns)
    graph.add_node("do_recall_metrics", recall_metrics)
    graph.add_node("do_recall_field_values", recall_field_values)
    graph.add_node("merge_retrieved_info", merge_retrieved_info_node)
    graph.add_node("filter_tables", filter_tables_node)
    graph.add_node("filter_columns", filter_columns_node)
    graph.add_node("filter_metrics", filter_metrics_node)
    graph.add_node("build_llm_context", build_llm_context)
    graph.add_node("plan_question", plan_question)
    graph.add_node("agent_loop", agent_loop)
    graph.add_node("build_agent_context", build_agent_context)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("generate_sql_step", generate_sql_step)
    graph.add_node("execute_plan_sql_step", execute_plan_sql_step)
    graph.add_node("assemble_result", assemble_result)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("correct_sql", correct_sql)
    graph.add_node("apply_policy", apply_policy)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("verify_answer", verify_answer)
    graph.add_node("format_answer", format_answer)

    graph.add_edge(START, "normalize_question")
    graph.add_edge("normalize_question", "load_session_memory")
    graph.add_edge("load_session_memory", "load_user_preference")
    graph.add_edge("load_user_preference", "resolve_references")
    graph.add_edge("resolve_references", "extract_keywords")
    graph.add_edge("extract_keywords", "do_recall_tables")
    if recall_columns_enabled:
        graph.add_edge("do_recall_tables", "do_recall_columns")
        graph.add_edge("do_recall_columns", "do_recall_metrics")
    else:
        graph.add_edge("do_recall_tables", "do_recall_metrics")
    graph.add_edge("do_recall_metrics", "do_recall_field_values")
    graph.add_edge("do_recall_field_values", "merge_retrieved_info")
    graph.add_edge("merge_retrieved_info", "filter_tables")
    graph.add_edge("filter_tables", "filter_columns")
    graph.add_edge("filter_columns", "filter_metrics")
    graph.add_edge("filter_metrics", "build_llm_context")
    graph.add_edge("build_llm_context", "plan_question")
    graph.add_conditional_edges(
        "plan_question",
        route_after_plan,
        {
            "generate_sql": "generate_sql",
            "agent_loop": "agent_loop",
            "format_answer": "format_answer",
        },
    )
    graph.add_conditional_edges(
        "agent_loop",
        route_after_agent_loop,
        {
            "agent_loop": "agent_loop",
            "build_agent_context": "build_agent_context",
        },
    )
    graph.add_conditional_edges(
        "build_agent_context",
        route_after_build_agent_context,
        {
            "execute_plan_sql_step": "execute_plan_sql_step",
            "generate_sql_step": "generate_sql_step",
            "format_answer": "format_answer",
        },
    )
    graph.add_conditional_edges(
        "execute_plan_sql_step",
        route_after_execute_plan_sql_step,
        {
            "execute_plan_sql_step": "execute_plan_sql_step",
            "assemble_result": "assemble_result",
            "format_answer": "format_answer",
        },
    )
    graph.add_conditional_edges(
        "assemble_result",
        route_after_assemble_result,
        {
            "verify_answer": "verify_answer",
            "format_answer": "format_answer",
        },
    )
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_edge("generate_sql_step", "validate_sql")
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
            "verify_answer": "verify_answer",
        },
    )
    graph.add_conditional_edges(
        "verify_answer",
        route_after_verify,
        {
            "format_answer": "format_answer",
            "correct_sql": "correct_sql",
        },
    )
    graph.add_edge("format_answer", END)

    return graph.compile()


@lru_cache
def _get_ask_graph_cached(recall_columns_enabled: bool):
    return build_ask_graph(recall_columns_enabled=recall_columns_enabled)


def get_ask_graph():
    """进程内单例编译图（随 RECALL_COLUMNS_ENABLED 缓存）。"""
    settings = get_settings()
    return _get_ask_graph_cached(settings.recall_columns_enabled)


def clear_ask_graph_cache() -> None:
    """图结构变更后清缓存（测试用）。"""
    _get_ask_graph_cached.cache_clear()
