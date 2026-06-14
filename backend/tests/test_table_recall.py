"""表级召回与过滤单测。"""

import pytest

from app.agent.context_builder import (
    expand_table_names_by_relations,
    filter_tables,
    merge_retrieved_info,
)
from app.meta.repository import RelationRow
from app.retrieval.hybrid import HybridRecallResult, RecalledColumn, RecalledMetric, RecalledTable
from config.settings import Settings


def _settings(**overrides) -> Settings:
    base = {
        "JWT_SECRET": "test-secret-min-32-chars-long-enough",
        "RECALL_TOP_K_TABLE": 20,
        "MAX_TABLES_IN_PROMPT": 10,
        "TABLE_RECALL_SCORE_MIN": 0.7,
    }
    base.update(overrides)
    return Settings(**base)


def test_filter_tables_prefers_table_recall(monkeypatch):
    monkeypatch.setattr(
        "app.agent.context_builder.get_allowed_tables",
        lambda: frozenset(
            {
                "sport_activity_qzs_record",
                "base_student",
                "noise_table",
            }
        ),
    )
    recall = HybridRecallResult(
        keywords=["学生"],
        tables=[
            RecalledTable(
                table_id=1,
                table_name="sport_activity_qzs_record",
                search_text="活动打卡",
                score=0.9,
                recall_mode="es_vector",
            ),
            RecalledTable(
                table_id=2,
                table_name="base_student",
                search_text="学生表",
                score=0.85,
                recall_mode="es_vector",
            ),
            RecalledTable(
                table_id=3,
                table_name="noise_table",
                search_text="无关",
                score=0.5,
                recall_mode="es_vector",
            ),
        ],
        columns=[
            RecalledColumn(
                column_id=1,
                table_id=1,
                table_name="sport_activity_qzs_record",
                column_name="sport_count",
                search_text="运动次数",
                score=0.95,
                recall_mode="es_vector",
            )
        ],
    )
    merged = merge_retrieved_info(recall)
    merged = filter_tables(merged, _settings(), relations=[])
    assert "sport_activity_qzs_record" in merged.table_names
    assert "base_student" in merged.table_names
    assert "noise_table" not in merged.table_names


def test_expand_table_names_by_relations(monkeypatch):
    monkeypatch.setattr(
        "app.agent.context_builder.get_allowed_tables",
        lambda: frozenset({"sport_activity_qzs_record", "base_student"}),
    )
    rel = RelationRow(
        id=1,
        from_table_id=1,
        from_table_name="sport_activity_qzs_record",
        from_column="people_id",
        to_table_id=2,
        to_table_name="base_student",
        to_column="id",
        relation_type="logical_join",
        join_hint="sport_activity_qzs_record.people_id = base_student.id",
        cardinality="n:1",
        status=1,
    )
    expanded = expand_table_names_by_relations(
        ["sport_activity_qzs_record"],
        [rel],
        max_tables=10,
    )
    assert expanded == ["sport_activity_qzs_record", "base_student"]


def test_filter_tables_excludes_disabled_tables_from_metrics(monkeypatch):
    """指标 relevant_tables 引用已停用表时，不得进入候选表。"""
    monkeypatch.setattr(
        "app.agent.context_builder.get_allowed_tables",
        lambda: frozenset(
            {
                "base_school",
                "base_student",
                "sport_activity_qzs_time",
                "sport_activity_new",
                "sport_project",
            }
        ),
    )
    recall = HybridRecallResult(
        keywords=["跳绳"],
        tables=[
            RecalledTable(
                table_id=1,
                table_name="sport_activity_qzs_time",
                search_text="打卡时间",
                score=0.68,
                recall_mode="es_vector",
            ),
            RecalledTable(
                table_id=2,
                table_name="base_student",
                search_text="学生",
                score=0.69,
                recall_mode="es_vector",
            ),
        ],
        metrics=[
            RecalledMetric(
                metric_id=1,
                metric_code="qzs_month_participants",
                metric_name="当月参与人数",
                search_text="",
                score=0.85,
                recall_mode="es_vector",
                relevant_tables="sport_activity_qzs_record",
            ),
        ],
    )
    merged = merge_retrieved_info(recall)
    merged = filter_tables(merged, _settings(), relations=[])
    assert "sport_activity_qzs_record" not in merged.table_names
    assert "sport_activity_qzs_time" in merged.table_names
    assert "base_student" in merged.table_names
