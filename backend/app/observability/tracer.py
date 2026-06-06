"""
问数可观测：写入 copilot_ask_turn / copilot_ask_span / copilot_audit_log。

MVP 阶段记录单次 /ask 的端到端耗时与审计哈希，供运营排查与合规留痕。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext


async def insert_turn_start(
    session: AsyncSession,
    *,
    trace_id: str,
    session_id: str | None,
    ctx: UserContext,
    question: str,
) -> None:
    """问数开始时插入 copilot_ask_turn（status=pending）。"""
    await session.execute(
        text(
            """
            INSERT INTO copilot_ask_turn (
                trace_id, session_id, user_id, role, active_sch_id,
                question, status, degrade_level
            ) VALUES (
                :trace_id, :session_id, :user_id, :role, :active_sch_id,
                :question, 'pending', 0
            )
            """
        ),
        {
            "trace_id": trace_id,
            "session_id": session_id,
            "user_id": ctx.user_id,
            "role": ctx.role.value,
            "active_sch_id": ctx.active_sch_id,
            "question": question,
        },
    )


async def insert_span(
    session: AsyncSession,
    *,
    trace_id: str,
    node_name: str,
    started_at: datetime,
    duration_ms: int,
    status: str,
    detail: dict | None = None,
) -> None:
    """记录 LangGraph 节点级 Span（MVP 用手动节点名）。"""
    await session.execute(
        text(
            """
            INSERT INTO copilot_ask_span (
                trace_id, node_name, started_at, duration_ms, status, detail_json
            ) VALUES (
                :trace_id, :node_name, :started_at, :duration_ms, :status, :detail_json
            )
            """
        ),
        {
            "trace_id": trace_id,
            "node_name": node_name,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "status": status,
            "detail_json": json.dumps(detail, ensure_ascii=False) if detail else None,
        },
    )


async def finish_turn(
    session: AsyncSession,
    *,
    trace_id: str,
    status: str,
    final_sql: str | None,
    latency_ms_total: int,
    latency_ms_sql_exec: int | None = None,
    latency_ms_sql_gen: int | None = None,
    latency_ms_first_token: int | None = None,
    row_count: int | None = None,
    error_code: str | None = None,
    degrade_level: int = 0,
    retry_count: int = 0,
    token_in: int | None = None,
    token_out: int | None = None,
    trace_log: str | None = None,
) -> None:
    """更新 copilot_ask_turn 为终态。"""
    await session.execute(
        text(
            """
            UPDATE copilot_ask_turn SET
                final_sql = :final_sql,
                status = :status,
                degrade_level = :degrade_level,
                error_code = :error_code,
                latency_ms_total = :latency_ms_total,
                latency_ms_first_token = :latency_ms_first_token,
                latency_ms_sql_exec = :latency_ms_sql_exec,
                latency_ms_sql_gen = :latency_ms_sql_gen,
                row_count = :row_count,
                retry_count = :retry_count,
                token_in = :token_in,
                token_out = :token_out,
                trace_log = :trace_log
            WHERE trace_id = :trace_id
            """
        ),
        {
            "trace_id": trace_id,
            "final_sql": final_sql,
            "status": status,
            "degrade_level": degrade_level,
            "error_code": error_code,
            "latency_ms_total": latency_ms_total,
            "latency_ms_first_token": latency_ms_first_token,
            "latency_ms_sql_exec": latency_ms_sql_exec,
            "latency_ms_sql_gen": latency_ms_sql_gen,
            "row_count": row_count,
            "retry_count": retry_count,
            "token_in": token_in,
            "token_out": token_out,
            "trace_log": trace_log,
        },
    )


async def insert_audit(
    session: AsyncSession,
    *,
    ctx: UserContext,
    trace_id: str,
    question: str,
    sql: str | None,
    tables_used: str | None,
    row_count: int | None,
) -> None:
    """写入合规审计日志（SQL 仅存哈希）。"""
    sql_hash = None
    if sql:
        sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    await session.execute(
        text(
            """
            INSERT INTO copilot_audit_log (
                trace_id, user_id, role, active_sch_id, question,
                sql_hash, tables_used, row_count, client_ip
            ) VALUES (
                :trace_id, :user_id, :role, :active_sch_id, :question,
                :sql_hash, :tables_used, :row_count, :client_ip
            )
            """
        ),
        {
            "trace_id": trace_id,
            "user_id": ctx.user_id,
            "role": ctx.role.value,
            "active_sch_id": ctx.active_sch_id,
            "question": question,
            "sql_hash": sql_hash,
            "tables_used": tables_used,
            "row_count": row_count,
            "client_ip": ctx.client_ip,
        },
    )
