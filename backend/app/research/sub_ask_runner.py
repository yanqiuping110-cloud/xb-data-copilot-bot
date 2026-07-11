"""内层问数封装：单节调用 run_ask_graph / stream_ask_graph。"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.log_utils import get_node_label
from app.agent.runner import run_ask_graph, stream_ask_graph
from app.core.context import UserContext
from app.research.pipeline import is_tool_node, pipeline_step_for_node
from app.schemas.ask import AskRequest, AskResponse
from config.settings import Settings


def _parse_sse_frame(frame: str) -> tuple[str, dict[str, Any]]:
    event_name = "message"
    data_line = ""
    for line in frame.split("\n"):
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_line += line[5:].strip()
    payload: dict[str, Any] = {}
    if data_line:
        payload = json.loads(data_line)
    return event_name, payload


def _result_from_response(resp: AskResponse | dict[str, Any], *, section_index: int, latency_ms: int) -> dict[str, Any]:
    if isinstance(resp, AskResponse):
        data = resp
    else:
        data = AskResponse.model_validate(resp)
    chart_spec = None
    if data.chart_spec is not None:
        chart_spec = data.chart_spec.model_dump(by_alias=True, mode="json")
    return {
        "section_index": section_index,
        "status": data.status if data.status in ("success", "degraded") else "fail",
        "answer": data.answer,
        "columns": data.columns,
        "rows": data.rows,
        "chart_spec": chart_spec,
        "sub_trace_id": data.trace_id,
        "error_code": data.error_code,
        "latency_ms": data.latency_ms or latency_ms,
    }


async def run_section_ask(
    *,
    question: str,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
    session_id: str | None,
    parent_report_id: str,
    section_index: int,
) -> dict[str, Any]:
    """执行单节问数并返回结构化结果（JSON 模式）。"""
    t0 = time.perf_counter()
    sub_trace_id = f"trace-{uuid.uuid4().hex[:24]}"
    body = AskRequest(question=question, session_id=session_id, trace_id=sub_trace_id)
    _ = parent_report_id
    try:
        resp = await run_ask_graph(body, ctx, copilot_session, settings)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return _result_from_response(resp, section_index=section_index, latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "section_index": section_index,
            "status": "fail",
            "answer": None,
            "columns": None,
            "rows": None,
            "chart_spec": None,
            "sub_trace_id": sub_trace_id,
            "error_code": "SECTION_ASK_ERROR",
            "latency_ms": latency_ms,
            "error_message": str(exc)[:300],
        }


async def stream_section_ask(
    *,
    question: str,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
    session_id: str | None,
    parent_report_id: str,
    section_index: int,
) -> AsyncIterator[dict[str, Any]]:
    """
    流式单节问数：转发内层 progress/done/error，供 Research SSE 映射。

    Yields dict events:
      - progress: { pipeline_step, label, node, tool? }
      - done: { result }
      - preview: { columns, rows_sample }
      - chart: { chart_spec }
      - error: { code, message }
    """
    t0 = time.perf_counter()
    sub_trace_id = f"trace-{uuid.uuid4().hex[:24]}"
    body = AskRequest(question=question, session_id=session_id, trace_id=sub_trace_id)
    _ = parent_report_id

    try:
        async for frame in stream_ask_graph(body, ctx, copilot_session, settings):
            event, payload = _parse_sse_frame(frame)
            if event == "progress":
                node = payload.get("node") or ""
                label = payload.get("label") or get_node_label(node)
                tool = label if is_tool_node(node) else None
                yield {
                    "type": "progress",
                    "pipeline_step": pipeline_step_for_node(node),
                    "label": label,
                    "node": node,
                    "tool": tool,
                }
            elif event == "text_delta":
                yield {"type": "text_delta", "delta": payload.get("delta") or ""}
            elif event == "done":
                latency_ms = int((time.perf_counter() - t0) * 1000)
                result = _result_from_response(payload, section_index=section_index, latency_ms=latency_ms)
                yield {"type": "done", "result": result}
                if result.get("columns") and result.get("rows"):
                    yield {
                        "type": "preview",
                        "columns": result["columns"],
                        "rows_sample": (result["rows"] or [])[:3],
                    }
                if result.get("chart_spec"):
                    yield {"type": "chart", "chart_spec": result["chart_spec"]}
            elif event == "error":
                yield {
                    "type": "error",
                    "code": payload.get("code") or "SECTION_ASK_ERROR",
                    "message": payload.get("message") or "问数失败",
                }
                latency_ms = int((time.perf_counter() - t0) * 1000)
                yield {
                    "type": "done",
                    "result": {
                        "section_index": section_index,
                        "status": "fail",
                        "answer": None,
                        "columns": None,
                        "rows": None,
                        "chart_spec": None,
                        "sub_trace_id": sub_trace_id,
                        "error_code": payload.get("code"),
                        "latency_ms": latency_ms,
                    },
                }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        yield {
            "type": "done",
            "result": {
                "section_index": section_index,
                "status": "fail",
                "answer": None,
                "columns": None,
                "rows": None,
                "chart_spec": None,
                "sub_trace_id": sub_trace_id,
                "error_code": "SECTION_ASK_ERROR",
                "latency_ms": latency_ms,
                "error_message": str(exc)[:300],
            },
        }
