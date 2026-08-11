"""
编译 LangGraph 问数有向图（对话门禁 + 多阶段召回 + Agent Loop + 分步 SQL + correct_sql）。
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.memory_nodes import (
    load_session_memory,
    load_user_preference,
    process_memory_context_node,
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
from app.agent.l1_nodes import recall_sql_examples_node, select_l1_examples_node
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
from app.agent.chart_nodes import build_chart
from app.agent.dialogue_nodes import (
    ask_clarification,
    reply_chat,
    route_after_dialogue,
    route_after_merge_recall,
    route_dialogue,
)
from app.agent.recall_nodes import (
    build_llm_context,
    extract_keywords_node,
    merge_retrieved_info_node,
    recall_field_values,
    recall_metrics,
    recall_tables,
)
from app.agent.verify_nodes import route_after_verify, verify_answer
from config.settings import get_settings
from app.agent.state import AskGraphState


def build_ask_graph(*, recall_columns_enabled: bool | None = None):
    """构建并编译问数 StateGraph。"""
    if recall_columns_enabled is None:
        recall_columns_enabled = get_settings().recall_columns_enabled

    graph = StateGraph(AskGraphState)

    # --- 预处理与记忆 / 门禁 ---
    graph.add_node("normalize_question", normalize_question)
    graph.add_node("load_session_memory", load_session_memory)
    graph.add_node("load_user_preference", load_user_preference)
    graph.add_node("route_dialogue", route_dialogue)
    graph.add_node("reply_chat", reply_chat)
    graph.add_node("ask_clarification", ask_clarification)
    graph.add_node("process_memory_context", process_memory_context_node)
    # --- 多阶段召回 ---
    graph.add_node("extract_keywords", extract_keywords_node)
    graph.add_node("do_recall_tables", recall_tables)
    if recall_columns_enabled:
        from app.agent.recall_nodes import recall_columns

        graph.add_node("do_recall_columns", recall_columns)
    graph.add_node("do_recall_metrics", recall_metrics)
    graph.add_node("do_recall_field_values", recall_field_values)
    graph.add_node("merge_retrieved_info", merge_retrieved_info_node)
    graph.add_node("do_recall_sql_examples", recall_sql_examples_node)
    graph.add_node("build_llm_context", build_llm_context)
    graph.add_node("select_l1_examples", select_l1_examples_node)
    # --- 规划与 Agent ---
    graph.add_node("plan_question", plan_question)
    graph.add_node("agent_loop", agent_loop)
    graph.add_node("build_agent_context", build_agent_context)
    # --- SQL 生成与分步执行 ---
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("generate_sql_step", generate_sql_step)
    graph.add_node("execute_plan_sql_step", execute_plan_sql_step)
    graph.add_node("assemble_result", assemble_result)
    # --- 校验、执行与答复 ---
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("correct_sql", correct_sql)
    graph.add_node("apply_policy", apply_policy)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("verify_answer", verify_answer)
    graph.add_node("build_chart", build_chart)
    graph.add_node("format_answer", format_answer)

    graph.add_edge(START, "normalize_question")
    graph.add_edge("normalize_question", "load_session_memory")
    graph.add_edge("load_session_memory", "load_user_preference")
    graph.add_edge("load_user_preference", "route_dialogue")
    graph.add_conditional_edges(
        "route_dialogue",
        route_after_dialogue,
        {
            "reply_chat": "reply_chat",
            "ask_clarification": "ask_clarification",
            "process_memory_context": "process_memory_context",
        },
    )
    graph.add_edge("reply_chat", "format_answer")
    graph.add_edge("ask_clarification", "format_answer")
    graph.add_edge("process_memory_context", "extract_keywords")
    graph.add_edge("extract_keywords", "do_recall_tables")
    if recall_columns_enabled:
        graph.add_edge("do_recall_tables", "do_recall_columns")
        graph.add_edge("do_recall_columns", "do_recall_metrics")
    else:
        graph.add_edge("do_recall_tables", "do_recall_metrics")
    graph.add_edge("do_recall_metrics", "do_recall_field_values")
    graph.add_edge("do_recall_field_values", "merge_retrieved_info")
    graph.add_conditional_edges(
        "merge_retrieved_info",
        route_after_merge_recall,
        {
            "ask_clarification": "ask_clarification",
            "do_recall_sql_examples": "do_recall_sql_examples",
            "format_answer": "format_answer",
        },
    )
    graph.add_edge("do_recall_sql_examples", "build_llm_context")
    graph.add_edge("build_llm_context", "select_l1_examples")
    graph.add_edge("select_l1_examples", "plan_question")
    graph.add_conditional_edges(
        "plan_question",
        route_after_plan,
        {
            "generate_sql": "generate_sql",
            "agent_loop": "agent_loop",
            "ask_clarification": "ask_clarification",
            "format_answer": "format_answer",
        },
    )
    graph.add_conditional_edges(
        "agent_loop",
        route_after_agent_loop,
        {
            "agent_loop": "agent_loop",
            "build_agent_context": "build_agent_context",
            "ask_clarification": "ask_clarification",
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
            "build_chart": "build_chart",
            "correct_sql": "correct_sql",
            "format_answer": "format_answer",
        },
    )
    graph.add_edge("build_chart", "format_answer")
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
