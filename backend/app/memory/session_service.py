"""
问数对话 Session 管理：列表、创建、删除、淘汰与归属校验。
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.memory.models import AskSessionRow
from app.observability.trace_log import parse_result_snapshot
from config.settings import Settings


class SessionError(Exception):
    """Session 业务异常。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SessionService:
    """copilot_ask_session 读写与每用户上限淘汰。"""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def list_sessions(self, user_id: int) -> list[AskSessionRow]:
        """当前用户未删除对话，按 updated_at 降序。"""
        limit = self._settings.session_max_per_user
        result = await self._session.execute(
            text(
                """
                SELECT session_id, title, turn_count, updated_at, created_at
                FROM copilot_ask_session
                WHERE user_id = :user_id AND deleted = 0
                ORDER BY updated_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
        rows: list[AskSessionRow] = []
        for row in result.mappings():
            rows.append(
                AskSessionRow(
                    session_id=row["session_id"],
                    title=row.get("title"),
                    turn_count=int(row.get("turn_count") or 0),
                    updated_at=row.get("updated_at"),
                    created_at=row.get("created_at"),
                )
            )
        return rows

    async def create_session(self, ctx: UserContext, *, title: str | None = None) -> str:
        """创建新对话；超限时按策略淘汰最旧。"""
        await self._evict_if_needed(ctx.user_id)
        session_id = f"sess-{uuid.uuid4().hex[:16]}"
        await self._session.execute(
            text(
                """
                INSERT INTO copilot_ask_session (
                    session_id, user_id, role, active_sch_id, title, turn_count
                ) VALUES (
                    :session_id, :user_id, :role, :active_sch_id, :title, 0
                )
                """
            ),
            {
                "session_id": session_id,
                "user_id": ctx.user_id,
                "role": ctx.role.value,
                "active_sch_id": ctx.active_sch_id,
                "title": title,
            },
        )
        return session_id

    async def delete_session(self, session_id: str, user_id: int) -> bool:
        """逻辑删除对话及关联摘要。"""
        owner = await self.verify_owner(session_id, user_id)
        if not owner:
            return False
        await self._session.execute(
            text(
                """
                UPDATE copilot_ask_session SET deleted = 1
                WHERE session_id = :session_id AND user_id = :user_id
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        await self._session.execute(
            text(
                """
                UPDATE copilot_session_summary SET deleted = 1
                WHERE session_id = :session_id AND user_id = :user_id
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        return True

    async def verify_owner(self, session_id: str, user_id: int) -> bool:
        """校验 session 归属当前用户。"""
        result = await self._session.execute(
            text(
                """
                SELECT 1 FROM copilot_ask_session
                WHERE session_id = :session_id AND user_id = :user_id AND deleted = 0
                LIMIT 1
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        return result.first() is not None

    async def session_belongs_to_other_user(self, session_id: str, user_id: int) -> bool:
        """session 已存在且不属于当前用户。"""
        result = await self._session.execute(
            text(
                """
                SELECT user_id FROM copilot_ask_session
                WHERE session_id = :session_id AND deleted = 0
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        )
        row = result.mappings().first()
        if row is None:
            return False
        return int(row["user_id"]) != user_id

    async def upsert_on_ask(
        self,
        session_id: str,
        ctx: UserContext,
        question: str,
        *,
        success: bool = False,
    ) -> None:
        """
        问数时 upsert 会话：首问写 title，每轮更新 updated_at；成功时 turn_count+1。
        """
        title = (question or "").strip()[:20] or "新对话"
        snapshot = json.dumps(
            {"role": ctx.role.value, "active_sch_id": ctx.active_sch_id},
            ensure_ascii=False,
        )
        await self._session.execute(
            text(
                """
                INSERT INTO copilot_ask_session (
                    session_id, user_id, role, active_sch_id, title,
                    turn_count, context_snapshot_json
                ) VALUES (
                    :session_id, :user_id, :role, :active_sch_id, :title,
                    :turn_inc, :snapshot
                )
                ON DUPLICATE KEY UPDATE
                    updated_at = NOW(),
                    turn_count = turn_count + :turn_inc,
                    title = IF(title IS NULL OR title = '', VALUES(title), title)
                """
            ),
            {
                "session_id": session_id,
                "user_id": ctx.user_id,
                "role": ctx.role.value,
                "active_sch_id": ctx.active_sch_id,
                "title": title,
                "turn_inc": 1 if success else 0,
                "snapshot": snapshot,
            },
        )

    async def list_messages(
        self,
        session_id: str,
        user_id: int,
        *,
        limit: int | None = None,
    ) -> list[dict]:
        """加载对话 UI 历史（与 Memory 同源 copilot_ask_turn）。"""
        if not await self.verify_owner(session_id, user_id):
            raise SessionError("FORBIDDEN", "无权访问该对话", 403)

        ui_limit = limit or self._settings.session_ui_turn_limit
        result = await self._session.execute(
            text(
                """
                SELECT trace_id, question, final_sql, status, row_count, created_at,
                       result_json, trace_log, error_code, latency_ms_total
                FROM (
                    SELECT t.trace_id, t.question, t.final_sql, t.status,
                           t.row_count, t.created_at, t.result_json, t.trace_log,
                           t.error_code, t.latency_ms_total
                    FROM copilot_ask_turn t
                    WHERE t.session_id = :session_id
                      AND t.user_id = :user_id
                      AND t.deleted = 0
                      AND t.status IN ('success', 'fail', 'degraded', 'cancelled')
                    ORDER BY t.created_at DESC
                    LIMIT :limit
                ) sub
                ORDER BY created_at ASC
                """
            ),
            {"session_id": session_id, "user_id": user_id, "limit": ui_limit},
        )
        messages: list[dict] = []
        for row in result.mappings():
            snapshot = parse_result_snapshot(
                row.get("result_json"),
                trace_log=row.get("trace_log"),
            )
            status = row["status"]
            answer = snapshot.get("answer")
            error_message = snapshot.get("error_message")
            if status == "cancelled" and not answer:
                answer = error_message or "用户主动中断"
            if status != "success" and status != "cancelled" and not answer:
                answer = error_message or row.get("error_code")
            messages.append(
                {
                    "trace_id": row["trace_id"],
                    "question": row["question"],
                    "final_sql": row.get("final_sql"),
                    "status": status,
                    "row_count": row.get("row_count"),
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    "answer": answer,
                    "columns": snapshot.get("columns"),
                    "rows": snapshot.get("rows"),
                    "error_message": error_message,
                    "latency_ms": row.get("latency_ms_total"),
                    "assembly_mode": snapshot.get("assembly_mode"),
                    "intermediate_results": snapshot.get("intermediate_results"),
                }
            )
        return messages

    async def _count_active(self, user_id: int) -> int:
        result = await self._session.execute(
            text(
                """
                SELECT COUNT(*) AS cnt FROM copilot_ask_session
                WHERE user_id = :user_id AND deleted = 0
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        return int(row["cnt"]) if row else 0

    async def _evict_if_needed(self, user_id: int) -> None:
        """创建新对话前检查上限，oldest 策略淘汰最旧一条。"""
        max_n = self._settings.session_max_per_user
        count = await self._count_active(user_id)
        if count < max_n:
            return
        if self._settings.session_evict_policy == "reject":
            raise SessionError(
                "SESSION_LIMIT",
                f"对话数量已达上限（{max_n}），请删除旧对话后再新建",
                409,
            )
        result = await self._session.execute(
            text(
                """
                SELECT session_id FROM copilot_ask_session
                WHERE user_id = :user_id AND deleted = 0
                ORDER BY updated_at ASC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        if row:
            await self.delete_session(row["session_id"], user_id)
