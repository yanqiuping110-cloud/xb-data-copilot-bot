"""L1 库内样例匹配单元测试（不依赖数据库）。"""

import pytest

from app.ask.curated_matcher import match_curated
from app.ask.query_match import ensure_can_run
from app.ask.semantic_repository import CuratedSqlExample
from app.core.context import UserContext, UserRole
from app.policy.role_policy import PolicyError

_QZS = "sport_activity_qzs_record"


def _example(**kwargs) -> CuratedSqlExample:
    defaults = {
        "id": 1,
        "question_pattern": "test",
        "sql_text": f"SELECT COUNT(*) AS cnt FROM {_QZS} WHERE 1=1",
        "role_scope": None,
        "degrade_priority": 10,
        "meta": {},
    }
    defaults.update(kwargs)
    return CuratedSqlExample(**defaults)


def _school(active: int | None) -> UserContext:
    return UserContext(
        trace_id="t",
        user_id=1,
        username="sch",
        role=UserRole.SCHOOL,
        active_sch_id=active,
        bound_sch_ids=[1140],
    )


def test_curated_month_with_project_id():
    ex = _example(
        meta={
            "matchAllGroups": [["参与", "参与人数"], ["本月", "这个月"]],
            "answerTemplate": "人数 {cnt}",
            "tables": [_QZS],
        }
    )
    matched = match_curated("本校本月跳绳活动参与人数是多少？", _school(1140), [ex])
    assert matched is not None
    assert matched.degrade_level == 1
    assert matched.match_source == "curated"
    assert "project_id = 1" in matched.sql
    assert "sch_id = :sch_id" in matched.sql


def test_curated_platform_blocked_for_school():
    ex = _example(
        meta={
            "matchAny": ["全平台"],
            "adminOnly": True,
            "requiresSchoolFilter": False,
            "tables": [_QZS],
        }
    )
    matched = match_curated("昨日全平台活动参与人次", _school(1140), [ex])
    assert matched is None


def test_curated_platform_for_admin():
    ex = _example(
        sql_text=f"SELECT COUNT(*) AS cnt FROM {_QZS} WHERE DATE(create_time) = CURDATE()",
        meta={"matchAny": ["全平台"], "adminOnly": True, "requiresSchoolFilter": False},
    )
    ctx = UserContext(trace_id="t", user_id=1, username="admin", role=UserRole.ADMIN)
    matched = match_curated("昨日全平台活动参与人次", ctx, [ex])
    assert matched is not None
    assert "sch_id" not in matched.sql.lower()


def test_ensure_can_run_school():
    ex = _example(
        meta={"matchAll": ["参与人数"], "tables": [_QZS]},
    )
    matched = match_curated("参与人数", _school(None), [ex])
    assert matched is not None
    with pytest.raises(PolicyError) as exc:
        ensure_can_run(matched, _school(None))
    assert exc.value.code == "NO_ACTIVE_SCHOOL"
