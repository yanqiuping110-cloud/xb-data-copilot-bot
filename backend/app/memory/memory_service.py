"""
Agent Memory 读取与 Prompt 拼装（Fail-open）。
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import SessionMemory, SessionTurnSlot, UserPreferenceItem
from app.memory.preference_keys import PREFERENCE_KEY_WHITELIST
from config.settings import Settings

logger = logging.getLogger(__name__)

# 从 final_sql 粗略提取 FROM/JOIN 表名
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)",
    flags=re.IGNORECASE,
)


class MemoryService:
    """会话槽位与用户偏好加载。"""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def load_session_memory(
        self,
        session_id: str | None,
        user_id: int,
    ) -> SessionMemory:
        """
        按 session_id 读最近 N 轮成功 turn，构建结构化槽位。

        任意失败返回 skipped=True（Fail-open，不阻断问数）。
        """
        empty = SessionMemory(session_id=session_id or "")
        if not self._settings.memory_enabled or not self._settings.session_memory_enabled:
            empty.skipped = True
            empty.skip_reason = "disabled"
            return empty
        if not session_id:
            empty.skipped = True
            empty.skip_reason = "no_session_id"
            return empty

        try:
            owner = await self._session.execute(
                text(
                    """
                    SELECT user_id FROM copilot_ask_session
                    WHERE session_id = :session_id AND deleted = 0
                    LIMIT 1
                    """
                ),
                {"session_id": session_id},
            )
            owner_row = owner.mappings().first()
            if owner_row is None:
                empty.skipped = True
                empty.skip_reason = "session_not_found"
                return empty
            if int(owner_row["user_id"]) != user_id:
                empty.skipped = True
                empty.skip_reason = "forbidden_session"
                logger.warning(
                    "memory forbidden session_id=%s user_id=%s",
                    session_id,
                    user_id,
                )
                return empty

            max_turns = self._settings.session_memory_max_turns
            result = await self._session.execute(
                text(
                    """
                    SELECT trace_id, question, final_sql, row_count, created_at
                    FROM copilot_ask_turn
                    WHERE session_id = :session_id
                      AND user_id = :user_id
                      AND deleted = 0
                      AND status = 'success'
                      AND final_sql IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "limit": max_turns,
                },
            )
            turns: list[SessionTurnSlot] = []
            for row in result.mappings():
                sql = row.get("final_sql") or ""
                tables = ", ".join(_TABLE_RE.findall(sql))
                turns.append(
                    SessionTurnSlot(
                        trace_id=row["trace_id"],
                        question=row["question"],
                        final_sql=sql,
                        tables_used=tables or None,
                        row_count=row.get("row_count"),
                        created_at=row.get("created_at"),
                    )
                )
            turns.reverse()

            summary_text = await self._load_summary(session_id, user_id)
            return SessionMemory(
                session_id=session_id,
                turns=turns,
                summary_text=summary_text,
            )
        except Exception as exc:
            logger.warning("load_session_memory fail-open: %s", exc)
            empty.skipped = True
            empty.skip_reason = str(exc)
            return empty

    async def _load_summary(self, session_id: str, user_id: int) -> str | None:
        result = await self._session.execute(
            text(
                """
                SELECT summary_text FROM copilot_session_summary
                WHERE session_id = :session_id AND user_id = :user_id AND deleted = 0
                LIMIT 1
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return row.get("summary_text")

    async def load_user_preferences(self, user_id: int) -> list[UserPreferenceItem]:
        """读取 explicit 白名单偏好（Fail-open）。"""
        if not self._settings.memory_enabled or not self._settings.user_preference_enabled:
            return []
        try:
            result = await self._session.execute(
                text(
                    """
                    SELECT pref_key, pref_value, source
                    FROM copilot_user_preference
                    WHERE user_id = :user_id AND deleted = 0 AND source = 'explicit'
                    """
                ),
                {"user_id": user_id},
            )
            items: list[UserPreferenceItem] = []
            for row in result.mappings():
                key = row["pref_key"]
                if key not in PREFERENCE_KEY_WHITELIST:
                    continue
                raw = row.get("pref_value")
                if isinstance(raw, str):
                    try:
                        value = json.loads(raw)
                    except json.JSONDecodeError:
                        value = raw
                else:
                    value = raw
                items.append(
                    UserPreferenceItem(
                        pref_key=key,
                        pref_value=value,
                        source=row.get("source") or "explicit",
                    )
                )
            return items
        except Exception as exc:
            logger.warning("load_user_preferences fail-open: %s", exc)
            return []

    async def upsert_preferences(
        self,
        user_id: int,
        prefs: dict[str, object],
    ) -> list[UserPreferenceItem]:
        """批量 upsert 用户偏好（key 白名单）。"""
        saved: list[UserPreferenceItem] = []
        for key, value in prefs.items():
            if key not in PREFERENCE_KEY_WHITELIST:
                continue
            await self._session.execute(
                text(
                    """
                    INSERT INTO copilot_user_preference (user_id, pref_key, pref_value, source)
                    VALUES (:user_id, :pref_key, :pref_value, 'explicit')
                    ON DUPLICATE KEY UPDATE
                        pref_value = VALUES(pref_value),
                        source = 'explicit',
                        updated_at = NOW(),
                        deleted = 0
                    """
                ),
                {
                    "user_id": user_id,
                    "pref_key": key,
                    "pref_value": json.dumps(value, ensure_ascii=False),
                },
            )
            saved.append(UserPreferenceItem(pref_key=key, pref_value=value))
        return saved

    async def delete_preferences(self, user_id: int, keys: list[str] | None = None) -> int:
        """清空或按 key 删除偏好。"""
        if keys:
            count = 0
            for key in keys:
                if key not in PREFERENCE_KEY_WHITELIST:
                    continue
                await self._session.execute(
                    text(
                        """
                        UPDATE copilot_user_preference SET deleted = 1
                        WHERE user_id = :user_id AND pref_key = :pref_key
                        """
                    ),
                    {"user_id": user_id, "pref_key": key},
                )
                count += 1
            return count
        result = await self._session.execute(
            text(
                """
                UPDATE copilot_user_preference SET deleted = 1
                WHERE user_id = :user_id AND deleted = 0
                """
            ),
            {"user_id": user_id},
        )
        return result.rowcount or 0

    async def update_session_summary(
        self,
        session_id: str,
        user_id: int,
        memory: SessionMemory,
    ) -> None:
        """
        P1：超 3 轮时用规则压缩摘要（同步更新，无 LLM 调用）。
        """
        if len(memory.turns) < 3:
            return
        lines = [f"Q: {t.question[:80]}" for t in memory.turns[-3:]]
        summary = "；".join(lines)
        last = memory.last_turn
        slot = {
            "last_sql": (last.final_sql or "")[:500] if last else None,
            "last_tables": last.tables_used if last else None,
            "last_question": last.question if last else None,
        }
        await self._session.execute(
            text(
                """
                INSERT INTO copilot_session_summary (
                    session_id, user_id, summary_text, slot_json, turn_count
                ) VALUES (
                    :session_id, :user_id, :summary, :slot_json, :turn_count
                )
                ON DUPLICATE KEY UPDATE
                    summary_text = VALUES(summary_text),
                    slot_json = VALUES(slot_json),
                    turn_count = VALUES(turn_count),
                    updated_at = NOW()
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "summary": summary,
                "slot_json": json.dumps(slot, ensure_ascii=False),
                "turn_count": len(memory.turns),
            },
        )


def build_memory_prompt_sections(
    memory: SessionMemory | None,
    preferences: list[UserPreferenceItem],
    *,
    max_chars: int,
    inject_session: bool = True,
) -> tuple[str, dict]:
    """
    拼装【会话上下文】【用户偏好】Prompt 小节。

    Returns:
        (text, detail) detail 供 span 可观测。
    """
    parts: list[str] = []
    detail: dict = {
        "session_injected": False,
        "preference_count": 0,
        "truncated": False,
        "chars": 0,
    }

    if inject_session and memory and not memory.skipped and memory.turns:
        parts.append("【会话上下文（多轮指代参考，勿直接复制 SQL 绕过校验）】")
        last = memory.last_turn
        if last:
            parts.append(f"- 上一轮问句：{last.question[:200]}")
            if last.final_sql:
                sql_preview = " ".join(last.final_sql.split())[:400]
                parts.append(f"- 上一轮 SQL：{sql_preview}")
            if last.tables_used:
                parts.append(f"- 涉及表：{last.tables_used}")
            if last.row_count is not None:
                parts.append(f"- 上一轮结果行数：{last.row_count}")
        if memory.summary_text:
            parts.append(f"- 会话摘要：{memory.summary_text[:300]}")
        parts.append("")
        detail["session_injected"] = True

    explicit_prefs = [p for p in preferences if p.source == "explicit"]
    if explicit_prefs:
        parts.append("【用户偏好（显式）】")
        for pref in explicit_prefs:
            val = pref.pref_value
            if isinstance(val, (dict, list)):
                val_str = json.dumps(val, ensure_ascii=False)
            else:
                val_str = str(val)
            parts.append(f"- {pref.pref_key}：{val_str[:200]}")
        parts.append("")
        detail["preference_count"] = len(explicit_prefs)

    text_block = "\n".join(parts).strip()
    if len(text_block) > max_chars:
        text_block = text_block[: max_chars - 20] + "\n…（已截断）"
        detail["truncated"] = True
    detail["chars"] = len(text_block)
    return text_block, detail
