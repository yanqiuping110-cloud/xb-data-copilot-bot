"""L1 样例软参考排序与过滤单元测试。"""

import pytest

from app.ask.example_ranker import (
    is_example_visible_to_user,
    meta_rules_fully_match,
    rank_curated_examples_for_prompt,
    score_curated_example,
)
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


def test_meta_rules_fully_match_groups():
    meta = {"matchAllGroups": [["参与", "参与人数"], ["本月", "这个月"]]}
    assert meta_rules_fully_match("本校本月跳绳活动参与人数是多少？", meta)
    assert not meta_rules_fully_match("本校跳绳活动", meta)


def test_score_curated_example_jump_rope():
    ex = _example(
        question_pattern="本校本月活动参与人数",
        meta={
            "matchAllGroups": [["参与", "参与人数"], ["本月", "这个月"]],
            "tables": [_QZS],
        },
    )
    score = score_curated_example("本校本月跳绳活动参与人数是多少？", ex)
    assert score >= 12


def test_rank_filters_admin_only_for_school():
    ex = _example(
        meta={"matchAny": ["全平台"], "adminOnly": True, "requiresSchoolFilter": False},
    )
    assert not is_example_visible_to_user(ex, _school(1140))
    ranked = rank_curated_examples_for_prompt(
        "昨日全平台活动参与人次",
        _school(1140),
        [ex],
        top_k=5,
        min_score=1,
    )
    assert ranked == []


def test_rank_includes_admin_example_for_admin():
    ex = _example(
        sql_text=f"SELECT COUNT(*) AS cnt FROM {_QZS} WHERE DATE(create_time) = CURDATE()",
        meta={"matchAny": ["全平台"], "adminOnly": True, "requiresSchoolFilter": False},
    )
    ctx = UserContext(trace_id="t", user_id=1, username="admin", role=UserRole.ADMIN)
    ranked = rank_curated_examples_for_prompt(
        "昨日全平台活动参与人次",
        ctx,
        [ex],
        top_k=5,
        min_score=1,
    )
    assert len(ranked) == 1
    assert ranked[0][0].id == ex.id


def test_rank_respects_top_k_and_min_score():
    examples = [
        _example(id=1, question_pattern="无关样例", meta={}, degrade_priority=10),
        _example(
            id=2,
            question_pattern="本校本月活动参与人数",
            meta={"matchAll": ["参与人数", "本月"]},
            degrade_priority=20,
        ),
        _example(
            id=3,
            question_pattern="最近7天每日参与人数趋势",
            meta={"matchAllGroups": [["7", "七", "最近"], ["趋势", "每日"]]},
            degrade_priority=25,
        ),
    ]
    ranked = rank_curated_examples_for_prompt(
        "本校本月活动参与人数",
        _school(1140),
        examples,
        top_k=1,
        min_score=1,
    )
    assert len(ranked) == 1
    assert ranked[0][0].id == 2


def test_ensure_can_run_school():
    from app.ask.models import MatchedQuery

    matched = MatchedQuery(
        sql=f"SELECT COUNT(*) AS cnt FROM {_QZS} WHERE sch_id = :sch_id",
        tables=(_QZS,),
        value_column="cnt",
        answer_template="ok",
    )
    with pytest.raises(PolicyError) as exc:
        ensure_can_run(matched, _school(None))
    assert exc.value.code == "NO_ACTIVE_SCHOOL"
