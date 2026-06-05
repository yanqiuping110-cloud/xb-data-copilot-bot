"""元数据索引文本拼装单测。"""

from app.meta.index_text import (
    build_column_search_text,
    build_field_value_search_text,
    build_metric_search_text,
)
from app.meta.repository import IndexableColumnRow, IndexableFieldValueRow, IndexableMetricRow


def test_build_column_search_text_uses_manual():
    row = IndexableColumnRow(
        column_id=1,
        table_id=1,
        table_name="sport_activity_qzs_record",
        column_name="people_id",
        description_manual="参与人 ID",
        column_comment_auto="用户id",
        alias_json='["参与人","学生"]',
        column_role="dimension",
    )
    text = build_column_search_text(row)
    assert "sport_activity_qzs_record.people_id" in text
    assert "参与人 ID" in text
    assert "参与人" in text
    assert "用户id" not in text


def test_build_metric_search_text_includes_aliases():
    row = IndexableMetricRow(
        metric_id=1,
        metric_code="qzs_month_participants",
        metric_name="本校本月活动参与人数",
        description="当月去重 people_id",
        formula_text="COUNT(DISTINCT people_id)",
        relevant_tables="sport_activity_qzs_record",
        alias_json='["参与人数","本月参与"]',
    )
    text = build_metric_search_text(row)
    assert "本校本月活动参与人数" in text
    assert "COUNT(DISTINCT people_id)" in text
    assert "参与人数" in text


def test_build_field_value_search_text():
    row = IndexableFieldValueRow(
        field_value_id=1,
        column_id=10,
        table_name="sport_activity_qzs_record",
        column_name="project_id",
        value_text="1",
        display_label="跳绳",
        alias_json='["跳绳","跳绳项目"]',
    )
    text = build_field_value_search_text(row)
    assert "project_id=1" in text
    assert "跳绳" in text
