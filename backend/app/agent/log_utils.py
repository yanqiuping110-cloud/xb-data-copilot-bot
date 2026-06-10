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
    "resolve_references": "指代消解",
    "extract_keywords": "抽取关键词",
    "do_recall_tables": "召回相关表",
    "do_recall_columns": "召回相关字段",
    "do_recall_metrics": "召回相关指标",
    "do_recall_field_values": "召回字段取值",
    "merge_retrieved_info": "合并召回结果",
    "filter_tables": "筛选候选表",
    "filter_columns": "筛选 Prompt 字段",
    "filter_metrics": "筛选指标",
    "build_llm_context": "构建问数上下文",
    "generate_sql": "生成 SQL",
    "validate_sql": "校验 SQL",
    "correct_sql": "修正 SQL",
    "apply_policy": "应用权限策略",
    "execute_sql": "执行查询",
    "format_answer": "生成回答",
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
