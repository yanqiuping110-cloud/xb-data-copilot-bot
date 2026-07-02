"""plan_llm 辅助逻辑单测。"""

from app.agent.plan_llm import _PLAN_CONTEXT_MAX_CHARS, _truncate_plan_context


def test_truncate_plan_context_empty():
    assert _truncate_plan_context("") == ""
    assert _truncate_plan_context("   ") == ""


def test_truncate_plan_context_short_unchanged():
    text = "【候选表字段】sport_activity: user_id(用户)"
    assert _truncate_plan_context(text) == text


def test_truncate_plan_context_long_adds_notice():
    text = "x" * (_PLAN_CONTEXT_MAX_CHARS + 100)
    out = _truncate_plan_context(text)
    assert len(out) < len(text)
    assert "截断" in out
    assert out.startswith("x" * 100)
