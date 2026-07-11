"""SSE progress 载荷：phase / summary 脱敏 / icon。"""

from __future__ import annotations

from typing import Any

NODE_PHASE: dict[str, tuple[str, str]] = {
    "normalize_question": ("understand", "理解"),
    "load_session_memory": ("understand", "理解"),
    "load_user_preference": ("understand", "理解"),
    "process_memory_context": ("understand", "理解"),
    "extract_keywords": ("understand", "理解"),
    "do_recall_tables": ("recall", "召回"),
    "recall_tables": ("recall", "召回"),
    "do_recall_columns": ("recall", "召回"),
    "recall_columns": ("recall", "召回"),
    "do_recall_metrics": ("recall", "召回"),
    "recall_metrics": ("recall", "召回"),
    "do_recall_field_values": ("recall", "召回"),
    "recall_field_values": ("recall", "召回"),
    "merge_retrieved_info": ("recall", "召回"),
    "filter_tables": ("recall", "召回"),
    "filter_columns": ("recall", "召回"),
    "filter_metrics": ("recall", "召回"),
    "do_recall_sql_examples": ("recall", "召回"),
    "select_l1_examples": ("plan", "规划"),
    "plan_question": ("plan", "规划"),
    "build_llm_context": ("plan", "规划"),
    "agent_loop": ("plan", "规划"),
    "build_agent_context": ("plan", "规划"),
    "generate_sql": ("sql", "SQL"),
    "validate_sql": ("sql", "SQL"),
    "correct_sql": ("sql", "SQL"),
    "apply_policy": ("sql", "SQL"),
    "generate_sql_step": ("sql", "SQL"),
    "execute_plan_sql_step": ("sql", "SQL"),
    "execute_sql": ("execute", "执行"),
    "assemble_result": ("execute", "执行"),
    "verify_answer": ("execute", "执行"),
    "build_chart": ("answer", "回答"),
    "format_answer": ("answer", "回答"),
}

NODE_ICON: dict[str, str] = {
    "normalize_question": "edit",
    "load_session_memory": "collection",
    "load_user_preference": "collection",
    "process_memory_context": "collection",
    "extract_keywords": "search",
    "do_recall_tables": "search",
    "do_recall_columns": "search",
    "do_recall_metrics": "search",
    "do_recall_field_values": "search",
    "plan_question": "cpu",
    "agent_loop": "cpu",
    "generate_sql": "document",
    "validate_sql": "document",
    "execute_sql": "video-play",
    "execute_plan_sql_step": "video-play",
    "verify_answer": "video-play",
    "build_chart": "trend-charts",
    "format_answer": "chat-line-round",
}


def node_to_phase(node: str) -> tuple[str, str]:
    return NODE_PHASE.get(node, ("plan", "规划"))


def node_to_icon(node: str) -> str:
    return NODE_ICON.get(node, "cpu")


def build_progress_summary(node: str, detail: dict[str, Any] | None) -> str | None:
    """脱敏人话摘要：禁止物理表名/列名/SQL 片段。"""
    if not detail:
        return None

    if node == "extract_keywords":
        kws = detail.get("keywords") or []
        if kws:
            return "关键词：" + "、".join(str(k) for k in kws[:6])

    if node in (
        "do_recall_tables",
        "recall_tables",
        "do_recall_columns",
        "recall_columns",
        "do_recall_metrics",
        "recall_metrics",
        "do_recall_field_values",
        "recall_field_values",
    ):
        count = detail.get("count")
        if count is not None:
            label = "张候选表" if "table" in node else "项"
            if "table" in node:
                return f"命中 {count} {label}"
            return f"召回 {count} {label}"

    if node == "process_memory_context":
        ref = detail.get("referenceType") or detail.get("reference_type")
        if ref:
            return f"记忆整理 · {ref}"
        if detail.get("fallback"):
            return "记忆整理（降级）"

    if node == "do_recall_sql_examples":
        count = detail.get("count")
        if count is not None:
            return f"召回 {count} 条候选"

    if node == "select_l1_examples":
        count = detail.get("count")
        if count is not None:
            return f"精选 {count} 条" if count else "未选用 L1 样例"

    if node == "plan_question":
        complexity = detail.get("complexity")
        steps = detail.get("stepCount")
        if complexity and steps:
            return f"复杂度 {complexity} · {steps} 步"
        if complexity:
            return f"复杂度 {complexity}"

    if node in ("generate_sql", "generate_sql_step"):
        if detail.get("hasSql"):
            return "SQL 已生成"

    if node == "execute_sql":
        rc = detail.get("rowCount")
        if rc is not None:
            return f"返回 {rc} 行"

    if node == "execute_plan_sql_step":
        rc = detail.get("rowCount")
        if rc is not None:
            return f"本步返回 {rc} 行"

    if node == "assemble_result":
        rc = detail.get("rowCount")
        if rc is not None:
            return f"共 {rc} 行结果"

    if node == "verify_answer":
        if detail.get("passed"):
            return "语义验证通过"
        if detail.get("reason"):
            return "语义验证未通过"

    if node == "build_chart":
        return "图表已生成"

    if node == "format_answer":
        return "回答生成中"

    if node == "agent_loop":
        tool = detail.get("tool")
        if tool:
            return f"调用工具 {tool}"

    return None


def build_progress_body(
    node: str,
    *,
    detail: dict[str, Any] | None = None,
    status: str = "done",
    duration_ms: int | None = None,
) -> dict[str, Any]:
    from app.agent.log_utils import get_node_label

    phase, phase_label = node_to_phase(node)
    summary = build_progress_summary(node, detail)
    body: dict[str, Any] = {
        "node": node,
        "label": get_node_label(node),
        "phase": phase,
        "phaseLabel": phase_label,
        "status": status,
        "icon": node_to_icon(node),
    }
    if summary:
        body["summary"] = summary
    if detail:
        body["detail"] = detail
    if duration_ms is not None:
        body["durationMs"] = duration_ms
    return body
