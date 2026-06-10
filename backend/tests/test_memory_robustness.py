"""Agent Memory 鲁棒性与 Feature Flag 单测。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory.memory_service import MemoryService, build_memory_prompt_sections
from app.memory.models import SessionMemory, SessionTurnSlot
from types import SimpleNamespace


def _settings(**overrides):
    """避免 .env 覆盖测试用 Settings。"""
    base = {
        "memory_enabled": True,
        "session_memory_enabled": True,
        "user_preference_enabled": True,
        "memory_prompt_max_chars": 100,
        "session_memory_max_turns": 3,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_load_session_memory_disabled():
    session = AsyncMock()
    svc = MemoryService(session, _settings(session_memory_enabled=False))
    mem = await svc.load_session_memory("sess-1", 1)
    assert mem.skipped is True
    assert mem.skip_reason == "disabled"
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_load_session_memory_no_session_id():
    session = AsyncMock()
    svc = MemoryService(session, _settings())
    mem = await svc.load_session_memory(None, 1)
    assert mem.skipped is True
    assert mem.skip_reason == "no_session_id"


@pytest.mark.asyncio
async def test_load_session_memory_forbidden_owner():
    session = AsyncMock()
    owner_row = MagicMock()
    owner_row.mappings.return_value.first.return_value = {"user_id": 999}
    session.execute = AsyncMock(return_value=owner_row)

    svc = MemoryService(session, _settings())
    mem = await svc.load_session_memory("sess-x", 1)
    assert mem.skipped is True
    assert mem.skip_reason == "forbidden_session"


@pytest.mark.asyncio
async def test_load_session_memory_fail_open_on_db_error():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db timeout"))

    svc = MemoryService(session, _settings())
    mem = await svc.load_session_memory("sess-1", 1)
    assert mem.skipped is True
    assert "db timeout" in (mem.skip_reason or "")


def test_memory_prompt_truncation():
    mem = SessionMemory(
        session_id="s",
        turns=[
            SessionTurnSlot(
                trace_id="t",
                question="Q" * 200,
                final_sql="SELECT " + "x" * 300,
                tables_used="t1",
                row_count=1,
            )
        ],
    )
    text, detail = build_memory_prompt_sections(mem, [], max_chars=80)
    assert len(text) <= 80
    assert detail["truncated"] is True
