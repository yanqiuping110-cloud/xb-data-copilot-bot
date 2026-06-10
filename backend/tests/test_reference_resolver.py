"""指代消解与 Memory Prompt 单测。"""

from app.memory.memory_service import build_memory_prompt_sections
from app.memory.models import SessionMemory, SessionTurnSlot, UserPreferenceItem
from app.memory.reference_resolver import resolve_references


def _memory_with_turn() -> SessionMemory:
    return SessionMemory(
        session_id="sess-1",
        turns=[
            SessionTurnSlot(
                trace_id="t1",
                question="本校本月跳绳参与人数",
                final_sql="SELECT COUNT(*) FROM sport_activity_qzs_record WHERE project_id=1",
                tables_used="sport_activity_qzs_record",
                row_count=42,
            )
        ],
    )


def test_resolve_no_reference():
    q, hint, matched = resolve_references("最近7天趋势", _memory_with_turn())
    assert q == "最近7天趋势"
    assert hint is None
    assert matched is False


def test_resolve_刚才():
    q, hint, matched = resolve_references("按刚才的维度再查一次", _memory_with_turn())
    assert matched is True
    assert hint is not None
    assert "跳绳" in hint


def test_build_memory_prompt_truncation():
    mem = _memory_with_turn()
    prefs = [
        UserPreferenceItem(pref_key="default_time_range", pref_value={"unit": "month"})
    ]
    text, detail = build_memory_prompt_sections(mem, prefs, max_chars=500)
    assert "上一轮问句" in text
    assert "default_time_range" in text
    assert detail["session_injected"] is True
    assert detail["preference_count"] == 1


def test_build_memory_skipped():
    mem = SessionMemory(session_id="s", skipped=True, skip_reason="disabled")
    text, detail = build_memory_prompt_sections(mem, [], max_chars=2000)
    assert text == ""
    assert detail["session_injected"] is False
