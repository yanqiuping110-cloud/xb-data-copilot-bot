"""L1 样例服务：可见性与 Prompt 格式化。"""

from app.ask.l1_service import (
    L1ExampleCandidate,
    append_l1_to_context,
    format_l1_prompt_lines,
    is_l1_visible,
    primary_l1_sql,
)
from app.core.context import UserContext, UserRole
from app.meta.repository import SqlExampleRow


def _row(**kwargs) -> SqlExampleRow:
    return SqlExampleRow(id=1, degrade_priority=100, **kwargs)


def test_is_l1_visible_skips_draft():
    ctx = UserContext(trace_id="t", user_id=1, username="u", role=UserRole.ADMIN)
    row = _row(
        question_pattern="q",
        sql_text="SELECT 1",
        description=None,
        meta_json='{"draft": true}',
        role_scope=None,
        review_status=1,
    )
    assert is_l1_visible(row, ctx) is False


def test_format_l1_prompt_lines_empty():
    assert format_l1_prompt_lines([]) == []


def test_primary_l1_sql_first_only():
    items = [
        L1ExampleCandidate(1, "q1", "SELECT 1", "d1"),
        L1ExampleCandidate(2, "q2", "SELECT 2", "d2"),
    ]
    assert primary_l1_sql(items) == "SELECT 1"


def test_append_l1_to_context():
    ex = L1ExampleCandidate(1, "本校参与人数", "SELECT COUNT(*) FROM t", "月度统计")
    out = append_l1_to_context("base", [ex])
    assert "本校参与人数" in out
    assert "SELECT COUNT(*)" in out
