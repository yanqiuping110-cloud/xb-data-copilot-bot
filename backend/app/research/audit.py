"""深度分析报告审计日志。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext


async def log_research_event(
    session: AsyncSession,
    *,
    ctx: UserContext,
    report_id: str,
    action: str,
    detail: str,
) -> None:
    """写入 copilot_audit_log（question 字段编码 action + 摘要）。"""
    role = ctx.role.value if hasattr(ctx.role, "value") else str(ctx.role)
    await session.execute(
        text(
            """
            INSERT INTO copilot_audit_log (
                trace_id, user_id, role, active_sch_id, question,
                sql_hash, tables_used, row_count, client_ip
            ) VALUES (
                :trace_id, :user_id, :role, :active_sch_id, :question,
                NULL, NULL, NULL, :client_ip
            )
            """
        ),
        {
            "trace_id": report_id,
            "user_id": ctx.user_id,
            "role": role,
            "active_sch_id": getattr(ctx, "active_sch_id", None),
            "question": f"[{action}] {detail[:480]}",
            "client_ip": getattr(ctx, "client_ip", None),
        },
    )
