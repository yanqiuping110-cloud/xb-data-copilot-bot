"""
问数全链路 trace 聚合：写入 copilot_ask_turn.trace_log。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

_MAX_JSON_BYTES = 512 * 1024
_MAX_SQL_LEN = 4096
_MAX_TEXT_PREVIEW = 500
_MAX_CONTEXT_TEXT_LEN = 131072  # build_*_context 调试：trace 内保留完整 Prompt 上限
_MAX_ROWS_SAMPLE = 2
_MAX_RESULT_ROWS = 100


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def sanitize_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """压缩节点 detail，避免 trace_log 过大。"""
    if not detail:
        return None

    out: dict[str, Any] = {}
    for key, value in detail.items():
        if key in ("sql", "final_sql", "raw_sql") and isinstance(value, str):
            out[key if key != "raw_sql" else "sql_preview"] = _truncate(value, _MAX_SQL_LEN)
        elif key == "context_text" and isinstance(value, str):
            if len(value) <= _MAX_CONTEXT_TEXT_LEN:
                out[key] = value
            else:
                out[key] = value[:_MAX_CONTEXT_TEXT_LEN] + f"\n…（已截断，总长 {len(value)} 字符）"
        elif key == "memory_prompt_text" and isinstance(value, str):
            if len(value) <= _MAX_CONTEXT_TEXT_LEN:
                out[key] = value
            else:
                out[key] = value[:_MAX_CONTEXT_TEXT_LEN] + f"\n…（已截断，总长 {len(value)} 字符）"
        elif key == "llm_output" and isinstance(value, str):
            out[key] = _truncate(value, _MAX_CONTEXT_TEXT_LEN)
        elif key == "llm_input" and isinstance(value, dict):
            out[key] = value
        elif key == "prompt_text" and isinstance(value, str):
            if len(value) <= _MAX_CONTEXT_TEXT_LEN:
                out[key] = value
            else:
                out[key] = value[:_MAX_CONTEXT_TEXT_LEN] + f"\n…（已截断，总长 {len(value)} 字符）"
        elif key == "rows" and isinstance(value, list):
            out[key] = {"count": len(value), "sample": value[:_MAX_ROWS_SAMPLE]}
        elif key == "answer" and isinstance(value, str):
            out["answer_preview"] = _truncate(value, _MAX_TEXT_PREVIEW)
        elif key in ("sql_params", "params") and isinstance(value, dict):
            # 绑定参数（如 scope_school_0）原样保留，供复盘还原真实 SQL
            out["sql_params"] = {str(k): v for k, v in value.items()}
        elif isinstance(value, str) and len(value) > _MAX_TEXT_PREVIEW:
            out[key] = _truncate(value, _MAX_TEXT_PREVIEW)
        else:
            out[key] = value
    return out


class TraceLogCollector:
    """单次问数内存 trace，finish 时序列化为 JSON 写入 turn 表。"""

    def __init__(self, trace_id: str, *, stream: bool = False) -> None:
        self.trace_id = trace_id
        self.stream = stream
        self.started_at = _utc_now_iso()
        self._seq = 0
        self._nodes: list[dict[str, Any]] = []
        self._fatals: list[dict[str, Any]] = []
        self.latency_ms_first_token: int | None = None

    def mark_first_token(self, latency_ms: int) -> None:
        """流式模式下记录首 token（首条 SSE progress）耗时，仅记一次。"""
        if self.latency_ms_first_token is None:
            self.latency_ms_first_token = latency_ms

    def duration_for_node(self, node: str) -> int | None:
        """最近一次该节点 span 的耗时（供 SSE progress 展示）。"""
        for entry in reversed(self._nodes):
            if entry.get("node") == node:
                raw = entry.get("duration_ms")
                return int(raw) if raw is not None else None
        return None

    def append_node(
        self,
        node: str,
        label: str,
        status: str,
        duration_ms: int,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._seq += 1
        self._nodes.append(
            {
                "seq": self._seq,
                "node": node,
                "label": label,
                "status": status,
                "duration_ms": duration_ms,
                "detail": sanitize_detail(detail),
            }
        )

    def append_fatal(
        self,
        *,
        error_code: str,
        error_message: str,
        node: str | None = None,
    ) -> None:
        self._fatals.append(
            {
                "type": "fatal",
                "node": node,
                "error_code": error_code,
                "error_message": error_message,
            }
        )

    def build_payload(
        self,
        *,
        status: str,
        latency_ms_total: int,
        error_code: str | None = None,
        error_message: str | None = None,
        error_node: str | None = None,
        final: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": 1,
            "trace_id": self.trace_id,
            "stream": self.stream,
            "started_at": self.started_at,
            "finished_at": _utc_now_iso(),
            "latency_ms_total": latency_ms_total,
            "status": status,
            "nodes": self._nodes,
        }
        if self.stream and self.latency_ms_first_token is not None:
            payload["latency_ms_first_token"] = self.latency_ms_first_token
        if self._fatals:
            payload["fatals"] = self._fatals
        if error_code:
            payload["error_code"] = error_code
        if error_message:
            payload["error_message"] = error_message
        if error_node:
            payload["error_node"] = error_node
        if final:
            payload["final"] = final
        return payload

    def to_json(
        self,
        *,
        status: str,
        latency_ms_total: int,
        error_code: str | None = None,
        error_message: str | None = None,
        error_node: str | None = None,
        final: dict[str, Any] | None = None,
    ) -> str:
        payload = self.build_payload(
            status=status,
            latency_ms_total=latency_ms_total,
            error_code=error_code,
            error_message=error_message,
            error_node=error_node,
            final=final,
        )
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text.encode("utf-8")) <= _MAX_JSON_BYTES:
            return text

        payload["truncated"] = True
        while payload["nodes"] and len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > _MAX_JSON_BYTES:
            payload["nodes"].pop(0)
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text.encode("utf-8")) > _MAX_JSON_BYTES:
            payload.pop("nodes", None)
            text = json.dumps(payload, ensure_ascii=False, default=str)
        return text


def resolve_error_node(
    collector: TraceLogCollector | None,
    *,
    error_code: str | None,
) -> str | None:
    """从 collector 节点列表推断失败节点。"""
    if collector is None or not error_code:
        return None
    for entry in reversed(collector._nodes):
        if entry.get("status") in ("fail", "empty", "degraded"):
            return str(entry.get("node"))
    if collector._fatals:
        fatal = collector._fatals[-1]
        if fatal.get("node"):
            return str(fatal["node"])
        return "fatal"
    return None


def build_final_summary(final_state: dict[str, Any]) -> dict[str, Any]:
    """从图终态提取写入 trace_log.final 的摘要。"""
    sql = final_state.get("final_sql") or final_state.get("raw_sql")
    answer = final_state.get("answer")
    rows = final_state.get("rows") or []
    summary: dict[str, Any] = {
        "degrade_level": final_state.get("degrade_level") or 0,
        "retry_count": final_state.get("retry_count") or 0,
        "row_count": len(rows),
    }
    if sql:
        summary["sql_preview"] = _truncate(str(sql), _MAX_SQL_LEN)
    sql_params = final_state.get("sql_params")
    if isinstance(sql_params, dict) and sql_params:
        summary["sql_params"] = {str(k): v for k, v in sql_params.items()}
    if answer:
        summary["answer_preview"] = _truncate(str(answer), _MAX_TEXT_PREVIEW)
    if rows:
        summary["rows_sample"] = rows[:_MAX_ROWS_SAMPLE]
    return summary


def build_result_json(
    *,
    answer: str | None = None,
    columns: list[str] | None = None,
    rows: list[list] | None = None,
    error_message: str | None = None,
    intermediate_results: list[dict] | None = None,
    assembly_mode: str | None = None,
    chart_spec: dict | None = None,
    visualization_intent: dict | None = None,
    clarification: dict | None = None,
    dialogue_act: str | None = None,
    max_rows: int = _MAX_RESULT_ROWS,
) -> str:
    """构建写入 copilot_ask_turn.result_json 的快照（供历史 UI 回放）。"""
    payload: dict[str, Any] = {}
    if answer:
        payload["answer"] = answer
    if columns:
        payload["columns"] = columns
    if rows:
        payload["rows"] = rows[:max_rows]
    if error_message:
        payload["error_message"] = error_message
    if assembly_mode:
        payload["assembly_mode"] = assembly_mode
    if intermediate_results:
        payload["intermediate_results"] = intermediate_results
    if chart_spec:
        payload["chart_spec"] = chart_spec
    if visualization_intent:
        payload["visualization_intent"] = visualization_intent
    if clarification:
        payload["clarification"] = clarification
    if dialogue_act:
        payload["dialogue_act"] = dialogue_act
    return json.dumps(payload, ensure_ascii=False, default=str)


def parse_result_snapshot(
    result_json: str | None,
    *,
    trace_log: str | None = None,
) -> dict[str, Any]:
    """解析 turn 结果快照；无 result_json 时从 trace_log.final 降级。"""
    if result_json:
        try:
            data = json.loads(result_json)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    if not trace_log:
        return {}

    try:
        data = json.loads(trace_log)
    except json.JSONDecodeError:
        return {}

    final = data.get("final") or {}
    out: dict[str, Any] = {}
    if final.get("answer_preview"):
        out["answer"] = final["answer_preview"]
    if final.get("rows_sample"):
        out["rows"] = final["rows_sample"]
    if data.get("error_message"):
        out["error_message"] = data["error_message"]
    return out
