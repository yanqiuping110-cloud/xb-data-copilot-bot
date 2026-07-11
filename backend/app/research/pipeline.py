"""LangGraph 节点 → 6 步流水线映射。"""

from __future__ import annotations

# 1 理解 → 2 召回 → 3 规划 → 4 SQL → 5 执行 → 6 回答
_NODE_STEP: dict[str, int] = {
    "normalize_question": 1,
    "load_session_memory": 1,
    "load_user_preference": 1,
    "resolve_references": 1,
    "extract_keywords": 1,
    "do_recall_tables": 2,
    "do_recall_columns": 2,
    "do_recall_metrics": 2,
    "do_recall_field_values": 2,
    "merge_retrieved_info": 2,
    "filter_tables": 2,
    "filter_columns": 2,
    "filter_metrics": 2,
    "plan_question": 3,
    "build_llm_context": 3,
    "build_agent_context": 3,
    "agent_loop": 3,
    "generate_sql": 4,
    "generate_sql_step": 4,
    "validate_sql": 4,
    "correct_sql": 4,
    "apply_policy": 4,
    "execute_sql": 5,
    "execute_plan_sql_step": 5,
    "verify_answer": 5,
    "assemble_result": 5,
    "build_chart": 6,
    "format_answer": 6,
}


def pipeline_step_for_node(node: str) -> int:
    return _NODE_STEP.get(node, 3)


def is_tool_node(node: str) -> bool:
    return node.startswith("tool_")
