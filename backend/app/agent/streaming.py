"""
问数 SSE 流式事件：推送 LangGraph 节点进度与最终结果。
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.ask import AskResponse

# LangGraph 节点 → 前端展示文案
NODE_LABELS: dict[str, str] = {
    "normalize_question": "清洗问句",
    "extract_keywords": "抽取关键词",
    "recall_columns": "召回相关字段",
    "recall_metrics": "召回相关指标",
    "recall_field_values": "召回字段取值",
    "merge_retrieved_info": "合并召回结果",
    "filter_tables": "筛选候选表",
    "filter_metrics": "筛选指标",
    "build_llm_context": "构建问数上下文",
    "match_curated": "匹配样例 SQL",
    "generate_sql": "生成 SQL",
    "validate_sql": "校验 SQL",
    "correct_sql": "修正 SQL",
    "apply_policy": "应用权限策略",
    "execute_sql": "执行查询",
    "format_answer": "生成回答",
}


def format_sse(event: str, payload: dict[str, Any]) -> str:
    """组装 SSE 帧（event + data）。"""
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def progress_event(node: str, *, detail: dict[str, Any] | None = None) -> str:
    """节点进度事件。"""
    body: dict[str, Any] = {
        "node": node,
        "label": NODE_LABELS.get(node, node),
    }
    if detail:
        body["detail"] = detail
    return format_sse("progress", body)


def done_event(response: AskResponse) -> str:
    """流水线完成，携带与 POST /ask 一致的最终结果。"""
    payload = response.model_dump(by_alias=True, mode="json")
    return format_sse("done", payload)


def error_event(code: str, message: str) -> str:
    """流内业务错误（已开流后无法改 HTTP 状态码时使用）。"""
    return format_sse("error", {"code": code, "message": message})
