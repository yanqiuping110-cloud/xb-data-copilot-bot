"""Badcase → L1 草稿生成单测。"""

import json

from app.ask.example_ranker import rank_curated_examples_for_prompt
from app.ask.semantic_repository import CuratedSqlExample
from app.core.context import UserContext, UserRole
from app.memory.badcase_l1 import build_l1_draft_from_badcase, extract_tables_from_sql


def test_extract_tables():
    sql = "SELECT a FROM sport_activity_qzs_record r JOIN base_student s ON r.id = s.id"
    assert extract_tables_from_sql(sql) == ["sport_activity_qzs_record", "base_student"]


def test_build_draft_meta():
    draft = build_l1_draft_from_badcase(
        question="本校本月跳绳参与人数是多少？",
        sql_text="SELECT COUNT(*) AS cnt FROM sport_activity_qzs_record WHERE project_id=1",
        role="SCHOOL",
        trace_id="t-1",
    )
    meta = json.loads(draft["meta_json"])
    assert meta["draft"] is True
    assert meta["sourceTraceId"] == "t-1"
    assert "跳绳" in meta.get("matchAny", []) or "参与" in meta.get("matchAll", [])
    assert draft["degrade_priority"] == 999


def test_draft_example_not_in_soft_reference():
    draft = build_l1_draft_from_badcase(
        question="本校本月跳绳参与人数",
        sql_text="SELECT 1 AS cnt FROM sport_activity_qzs_record",
    )
    meta = json.loads(draft["meta_json"])
    ex = CuratedSqlExample(
        id=1,
        question_pattern=draft["question_pattern"],
        sql_text=draft["sql_text"],
        meta=meta,
        role_scope=None,
        degrade_priority=999,
    )
    ctx = UserContext(
        trace_id="t-test",
        user_id=1,
        username="u",
        role=UserRole.SCHOOL,
        active_sch_id=1,
    )
    ranked = rank_curated_examples_for_prompt(
        "本校本月跳绳参与人数",
        ctx,
        [ex],
        top_k=5,
        min_score=0,
    )
    assert ranked == []
