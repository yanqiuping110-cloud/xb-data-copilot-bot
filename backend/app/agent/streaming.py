"""
问数 SSE 流式事件：推送 LangGraph 节点进度与最终结果。
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.log_utils import NODE_LABELS, get_node_label
from app.schemas.ask import AskResponse


def format_sse(event: str, payload: dict[str, Any]) -> str:
    """组装 SSE 帧（event + data）。"""
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def progress_event(node: str, *, detail: dict[str, Any] | None = None) -> str:
    """节点进度事件。"""
    body: dict[str, Any] = {
        "node": node,
        "label": get_node_label(node),
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


def text_delta_event(delta: str) -> str:
    """回答文本增量（token/块级流式）。"""
    return format_sse("text_delta", {"delta": delta})


def thinking_delta_event(delta: str) -> str:
    """思考过程增量（DeepSeek reasoning_content）。"""
    return format_sse("thinking_delta", {"delta": delta})
