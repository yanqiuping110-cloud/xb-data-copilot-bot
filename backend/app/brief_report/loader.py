"""从 copilot_ask_turn 加载勾选轮次快照。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.brief_report.turn_quality import turn_has_reportable_content
from app.observability.trace_log import parse_result_snapshot


class BriefReportLoadError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def load_turns(
    session: AsyncSession,
    *,
    session_id: str,
    user_id: int,
    trace_ids: list[str],
) -> list[dict[str, Any]]:
    """按 trace_ids 顺序加载 turn；校验归属与 success 状态。"""
    if not trace_ids:
        raise BriefReportLoadError("EMPTY_TRACE_IDS", "请至少勾选一条问数记录")

    placeholders = ", ".join(f":tid{i}" for i in range(len(trace_ids)))
    params: dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
    }
    for i, tid in enumerate(trace_ids):
        params[f"tid{i}"] = tid

    result = await session.execute(
        text(
            f"""
            SELECT trace_id, question, final_sql, status, row_count, created_at,
                   result_json, trace_log
            FROM copilot_ask_turn
            WHERE session_id = :session_id
              AND user_id = :user_id
              AND deleted = 0
              AND trace_id IN ({placeholders})
            """
        ),
        params,
    )
    by_id: dict[str, dict[str, Any]] = {}
    for row in result.mappings():
        by_id[row["trace_id"]] = dict(row)

    turns: list[dict[str, Any]] = []
    for tid in trace_ids:
        row = by_id.get(tid)
        if row is None:
            raise BriefReportLoadError(
                "TRACE_NOT_FOUND",
                f"问数记录不存在或不属于当前会话：{tid}",
                403,
            )
        if row["status"] != "success":
            raise BriefReportLoadError(
                "TRACE_NOT_SUCCESS",
                f"仅支持成功的问数记录：{tid}",
                400,
            )
        snapshot = parse_result_snapshot(
            row.get("result_json"),
            trace_log=row.get("trace_log"),
        )
        turns.append(
            {
                "trace_id": tid,
                "question": row["question"],
                "final_sql": row.get("final_sql"),
                "status": row["status"],
                "row_count": row.get("row_count"),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "answer": snapshot.get("answer") or "",
                "columns": snapshot.get("columns") or [],
                "rows": snapshot.get("rows") or [],
                "chart_spec": snapshot.get("chart_spec"),
                "chart_image_url": snapshot.get("chart_image_url"),
                "visualization_intent": snapshot.get("visualization_intent"),
            }
        )

    weak = [t for t in turns if not turn_has_reportable_content(t)]
    if weak:
        sample = (weak[0].get("question") or weak[0]["trace_id"])[:32]
        raise BriefReportLoadError(
            "TRACE_NO_DATA",
            f"所选记录含无有效数据项（如「{sample}…」），请取消勾选后重试",
            400,
        )
    return turns
