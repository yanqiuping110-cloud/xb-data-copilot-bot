"""memory_llm STAR 记忆上下文单测。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.memory.memory_llm import (
    _apply_security_guards,
    build_llm_input_payload,
    process_memory_context_llm,
)
from app.memory.models import SessionMemory, SessionTurnSlot, UserPreferenceItem
from config.settings import get_settings


def _test_settings(**overrides):
    return get_settings().model_copy(update=overrides)


def _memory_with_project_sql() -> SessionMemory:
    return SessionMemory(
        session_id="sess-1",
        turns=[
            SessionTurnSlot(
                trace_id="t1",
                question="各项目本月运动人数",
                final_sql=(
                    "SELECT t2.project_name, COUNT(DISTINCT user_id) "
                    "FROM sport_activity_qzs_time t1 "
                    "JOIN sport_project t2 ON t1.project_id=t2.id GROUP BY t2.project_name"
                ),
                tables_used="sport_activity_qzs_time,sport_project",
                row_count=30,
            )
        ],
    )


def test_build_llm_input_payload_includes_turn_summaries():
    payload = build_llm_input_payload(
        question="那给我分析下3月份运动人数留存",
        memory=_memory_with_project_sql(),
        preferences=[],
        boundary_enabled=False,
    )
    assert payload["turn_count"] == 1
    assert "留存" in payload["current_question"]
    assert payload["turns"][0]["sql_summary"] is not None
    assert "project_name" in payload["turns"][0]["sql_summary"]


def test_security_guard_blocks_sql_on_new_topic():
    inject, inherit, ref = _apply_security_guards(
        {
            "reference_type": "new_topic",
            "inject": {
                "last_question": True,
                "last_sql": True,
                "last_tables": True,
            },
            "inherit": {"dimension_grain": "project"},
        },
        memory=_memory_with_project_sql(),
    )
    assert ref == "new_topic"
    assert inject["last_sql"] is False
    assert inherit["dimension_grain"] == "none"


@pytest.mark.asyncio
async def test_process_memory_context_llm_parses_star():
    llm_json = {
        "star": {
            "situation": "上一轮按项目统计运动人数",
            "task": "分析3月和4月全平台运动人数留存",
            "action": "新话题，不继承项目维度，不注入 SQL",
            "result": "全平台留存分析",
        },
        "reference_type": "new_topic",
        "resolved_question": "分析2026年3月和4月全平台运动人数留存",
        "recall_question": "3月4月运动人数留存",
        "inject": {
            "last_question": True,
            "last_sql": False,
            "last_tables": True,
            "session_summary": False,
            "preferences": True,
        },
        "inherit": {"dimension_grain": "platform", "time_range": True, "tables": True},
    }
    settings = _test_settings(memory_llm_enabled=True, memory_prompt_max_chars=2000)

    with patch(
        "app.agent.llm_client.complete_messages",
        new_callable=AsyncMock,
        return_value=(json.dumps(llm_json), None, 10, 20),
    ):
        result = await process_memory_context_llm(
            settings=settings,
            question="那给我分析下3月份运动人数留存和4月份运动留存",
            memory=_memory_with_project_sql(),
            preferences=[
                UserPreferenceItem(pref_key="default_time_range", pref_value={"unit": "month"})
            ],
        )

    assert result.fallback is False
    assert result.reference_type == "new_topic"
    assert result.inject["last_sql"] is False
    assert "全平台" in result.resolved_question
    assert result.star["situation"]
    assert "STAR" in result.memory_prompt_text
    assert result.llm_input["turn_count"] == 1
    assert result.token_in == 10


@pytest.mark.asyncio
async def test_process_memory_context_first_turn_skips_llm_call():
    settings = _test_settings(memory_llm_enabled=True)
    with patch(
        "app.agent.llm_client.complete_messages",
        new_callable=AsyncMock,
    ) as mock_llm:
        result = await process_memory_context_llm(
            settings=settings,
            question="本月运动人数",
            memory=SessionMemory(session_id="s1", turns=[]),
            preferences=[],
        )
        mock_llm.assert_not_called()
    assert result.memory_prompt_text == ""
    assert result.resolved_question == "本月运动人数"


@pytest.mark.asyncio
async def test_process_memory_context_disabled_fallback():
    settings = _test_settings(memory_llm_enabled=False)
    result = await process_memory_context_llm(
        settings=settings,
        question="本月运动人数",
        memory=_memory_with_project_sql(),
        preferences=[],
    )
    assert result.fallback is True
    assert result.inject["last_sql"] is False
