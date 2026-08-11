"""
问数节点状态增量摘要与中文标签，用于后台日志与 SSE 进度展示。
"""

from __future__ import annotations

from typing import Any

# LangGraph 图节点 → 中文含义（与 graph.py 节点名一致）
NODE_LABELS: dict[str, str] = {
    "normalize_question": "清洗问句",
    "load_session_memory": "加载会话记忆",
    "load_user_preference": "加载用户偏好",
    "process_memory_context": "记忆上下文",
    "route_dialogue": "对话分流",
    "reply_chat": "闲聊答复",
    "ask_clarification": "澄清提问",
    "ask_user_question": "向用户提问",
    "extract_keywords": "抽取关键词",
    "do_recall_tables": "召回相关表",
    "do_recall_columns": "召回相关字段",
    "do_recall_metrics": "召回相关指标",
    "do_recall_field_values": "召回字段取值",
    "merge_retrieved_info": "合并召回结果",
    "filter_tables": "筛选候选表",
    "filter_columns": "筛选 Prompt 字段",
    "filter_metrics": "筛选指标",
    "do_recall_sql_examples": "召回 L1 样例",
    "select_l1_examples": "精选 L1 样例",
    "build_llm_context": "构建问数上下文",
    "plan_question": "问句规划",
    "agent_loop": "Agent 工具循环",
    "build_agent_context": "构建 Agent 上下文",
    "generate_sql_step": "分步生成 SQL",
    "execute_plan_sql_step": "分步执行 SQL",
    "assemble_result": "组装查询结果",
    "tool_run_probe_sql": "工具·探查 SQL",
    "tool_describe_table": "工具·表结构",
    "tool_list_relations": "工具·表关系",
    "tool_get_join_path": "工具·JOIN路径",
    "tool_search_metrics": "工具·指标检索",
    "tool_search_field_values": "工具·取值检索",
    "tool_search_sql_examples": "工具·样例检索",
    "generate_sql": "生成 SQL",
    "validate_sql": "校验 SQL",
    "correct_sql": "修正 SQL",
    "apply_policy": "应用权限策略",
    "execute_sql": "执行查询",
    "verify_answer": "语义验证",
    "build_chart": "生成图表",
    "format_answer": "生成回答",
    "tool_search_code_artifacts": "工具·代码检索",
    "tool_get_code_artifact": "工具·代码片段",
    "tool_trace_code_flow": "工具·调用链",
    "tool_link_artifact_to_meta": "工具·代码关联元数据",
    "tool_ask_user_question": "工具·向用户提问",
}

# _span 等日志里使用的短节点名 → 图节点名
_NODE_ALIASES: dict[str, str] = {
    "recall_tables": "do_recall_tables",
    "recall_columns": "do_recall_columns",
    "recall_metrics": "do_recall_metrics",
    "recall_field_values": "do_recall_field_values",
}

STATUS_LABELS: dict[str, str] = {
    "success": "成功",
    "fail": "失败",
    "empty": "无结果",
    "degraded": "降级",
    "cancelled": "已中断",
}


def get_node_label(node: str) -> str:
    """返回节点中文含义；未知节点回退为英文名。"""
    key = _NODE_ALIASES.get(node, node)
    return NODE_LABELS.get(key, node)


def get_status_label(status: str) -> str:
    """返回节点执行状态中文含义。"""
    return STATUS_LABELS.get(status, status)


def summarize_state_update(update: dict[str, Any] | None) -> dict[str, Any]:
    """将 LangGraph 节点返回的 state 增量压缩为可读的日志字段。"""
    if not update:
        return {}

    summary: dict[str, Any] = {}
    for key, value in update.items():
        if key == "context_text" and isinstance(value, str):
            preview = value.replace("\n", " ")[:240]
            summary[key] = f"len={len(value)} preview={preview!r}"
        elif key in ("raw_sql", "final_sql") and isinstance(value, str):
            text = " ".join(value.split())
            summary[key] = text[:320] + ("..." if len(text) > 320 else "")
        elif key == "rows" and isinstance(value, list):
            summary[key] = {"count": len(value), "sample": value[:2]}
        elif key == "columns" and isinstance(value, list):
            summary[key] = value[:20]
        elif key == "recall_tables":
            summary[key] = [
                {"table": t.table_name, "score": round(t.score, 4)}
                for t in (value or [])[:10]
            ]
        elif key == "recall_columns":
            summary[key] = [
                {"table": c.table_name, "column": c.column_name, "score": round(c.score, 4)}
                for c in (value or [])[:8]
            ]
        elif key == "recall_metrics":
            summary[key] = [
                {"code": m.metric_code, "score": round(m.score, 4)}
                for m in (value or [])[:5]
            ]
        elif key == "recall_field_values":
            summary[key] = [
                {
                    "table": v.table_name,
                    "column": v.column_name,
                    "value": v.value_text,
                }
                for v in (value or [])[:5]
            ]
        elif key == "merged_recall" and value is not None:
            summary[key] = {
                "tables": getattr(value, "table_names", None),
                "table_recall_count": len(getattr(value, "recalled_tables", []) or []),
                "column_count": len(getattr(value, "columns", []) or []),
                "metric_count": len(getattr(value, "metrics", []) or []),
                "value_count": len(getattr(value, "field_values", []) or []),
                "prompt_columns": getattr(value, "prompt_columns", None),
            }
        elif key == "plan" and isinstance(value, dict):
            summary[key] = {
                "complexity": value.get("complexity"),
                "intent": value.get("intent"),
                "step_count": len(value.get("steps") or []),
                "visualization": value.get("visualization"),
            }
        elif key == "chart_spec" and isinstance(value, dict):
            summary[key] = {
                "chart_type": value.get("chart_type"),
                "status": value.get("status"),
            }
        elif key == "tool_observations" and isinstance(value, list):
            summary[key] = [{"tool": o.get("tool")} for o in value[:8]]
        elif key == "agent_steps" and isinstance(value, list):
            summary[key] = value[:8]
        elif key == "sql_steps" and isinstance(value, list):
            summary[key] = [{"step_id": s.get("step_id"), "goal": s.get("goal")} for s in value[:6]]
        elif key == "intermediate_results" and isinstance(value, list):
            summary[key] = [
                {
                    "step_id": ir.get("step_id"),
                    "goal": ir.get("goal"),
                    "row_count": ir.get("row_count"),
                }
                for ir in value[:6]
            ]
        elif key == "agent_step_count":
            summary[key] = value
        elif key == "matched" and value is not None:
            summary[key] = {
                "source": getattr(value, "match_source", None),
                "tables": list(getattr(value, "tables", []) or []),
            }
        elif key == "answer" and isinstance(value, str):
            summary[key] = value[:500] + ("..." if len(value) > 500 else "")
        else:
            summary[key] = value
    return summary
