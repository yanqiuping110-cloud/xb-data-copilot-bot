"""MVP 问句匹配单元测试。"""

import pytest

from app.ask.mvp_matcher import match_question
from app.ask.query_match import ensure_can_run
from app.core.context import UserContext, UserRole
from app.policy.role_policy import PolicyError


def _school(active: int | None, bound: list[int]) -> UserContext:
    return UserContext(
        trace_id="t",
        user_id=1,
        username="sch",
        role=UserRole.SCHOOL,
        active_sch_id=active,
        bound_sch_ids=bound,
    )


def test_match_month_participants():
    """本月参与人数应命中模板，跳绳问句带 project_id=1。"""
    matched = match_question("本校本月跳绳活动参与人数是多少？", _school(1140, [1140]))
    assert matched is not None
    assert "sch_id" in matched.sql
    assert "project_id = 1" in matched.sql
    assert "people_id" in matched.sql
    assert matched.params["sch_id"] == 1140


def test_school_no_platform_query():
    """学校账户不能匹配全平台问句。"""
    matched = match_question("昨日全平台活动参与人次汇总", _school(1140, [1140]))
    assert matched is None


def test_admin_platform_query():
    """超管可匹配全平台问句且无 sch_id。"""
    ctx = UserContext(
        trace_id="t",
        user_id=1,
        username="admin",
        role=UserRole.ADMIN,
    )
    matched = match_question("昨日全平台活动参与人次", ctx)
    assert matched is not None
    assert matched.admin_only is True
    assert "sch_id" not in matched.sql.lower()


def test_school_without_active_rejected():
    """未选学校时 ensure_can_run 对需校维度模板抛错。"""
    matched = match_question("本校本月参与人数", _school(None, [1140, 1220]))
    assert matched is not None
    with pytest.raises(PolicyError) as exc:
        ensure_can_run(matched, _school(None, [1140, 1220]))
    assert exc.value.code == "NO_ACTIVE_SCHOOL"
