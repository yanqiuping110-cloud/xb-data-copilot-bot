"""
Agent Memory 领域模型（进程内传递，非 ORM）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionTurnSlot:
    """单轮成功问数的结构化槽位。"""

    trace_id: str
    question: str
    final_sql: str | None
    tables_used: str | None
    row_count: int | None
    created_at: datetime | None = None


@dataclass
class SessionMemory:
    """会话短期记忆（L1）。"""

    session_id: str
    turns: list[SessionTurnSlot] = field(default_factory=list)
    summary_text: str | None = None
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def last_turn(self) -> SessionTurnSlot | None:
        return self.turns[-1] if self.turns else None


@dataclass
class UserPreferenceItem:
    """单条用户偏好。"""

    pref_key: str
    pref_value: dict | list | str | int | float | bool | None
    source: str = "explicit"


@dataclass
class AskSessionRow:
    """对话列表项。"""

    session_id: str
    title: str | None
    turn_count: int
    updated_at: datetime | None
    created_at: datetime | None
