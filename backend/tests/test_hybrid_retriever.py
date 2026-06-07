"""混合召回与多阶段上下文单测（无需 ES）。"""

from app.agent.context_builder import filter_metrics, merge_retrieved_info
from app.agent.nodes import route_after_validate
from app.meta.index_text import build_table_search_text
from app.meta.repository import IndexableColumnRow, IndexableFieldValueRow, IndexableMetricRow, IndexableTableRow
from app.retrieval.hybrid import (
    HybridRecallResult,
    RecalledColumn,
    RecalledMetric,
    rank_columns_by_keywords,
    rank_field_values_by_keywords,
    rank_metrics_by_keywords,
    rank_tables_by_keywords,
)
from app.retrieval.keyword_extractor import extract_keywords


def test_extract_keywords_chinese():
    kws = extract_keywords("本校本月跳绳活动参与人数是多少？")
    assert any("跳绳" in k for k in kws)
    assert any("参与" in k for k in kws)


def test_rank_tables_by_keywords():
    rows = [
        IndexableTableRow(
            table_id=1,
            table_name="sport_activity_qzs_record",
            table_role="fact",
            biz_domain="活动打卡",
            description_manual="亲子活动打卡记录",
            table_comment_auto=None,
            grain="每条打卡",
            column_summary="sport_count 运动次数 project_id 项目",
        ),
        IndexableTableRow(
            table_id=2,
            table_name="base_student",
            table_role="dim",
            biz_domain="学生",
            description_manual="学生主数据",
            table_comment_auto=None,
            grain=None,
            column_summary="name 学生姓名 in_year 入学年份",
        ),
    ]
    ranked = rank_tables_by_keywords(rows, ["学生", "打卡"], top_k=2)
    assert len(ranked) == 2
    assert {r.table_name for r in ranked} == {"sport_activity_qzs_record", "base_student"}


def test_build_table_search_text_includes_summary():
    row = IndexableTableRow(
        table_id=1,
        table_name="base_student",
        table_role="dim",
        biz_domain="学生",
        description_manual="学生表",
        table_comment_auto=None,
        grain=None,
        column_summary="name 学生姓名",
    )
    text = build_table_search_text(row)
    assert "base_student" in text
    assert "学生表" in text
    assert "name 学生姓名" in text


def test_rank_columns_scoped_to_tables():
    rows = [
        IndexableColumnRow(
            column_id=1,
            table_id=1,
            table_name="sport_activity_qzs_record",
            column_name="people_id",
            description_manual="参与人 ID",
            column_comment_auto="用户id",
            alias_json='["参与人","学生"]',
            column_role="dimension",
        ),
        IndexableColumnRow(
            column_id=2,
            table_id=1,
            table_name="sport_activity_qzs_record",
            column_name="sch_id",
            description_manual="学校 ID",
            column_comment_auto=None,
            alias_json=None,
            column_role="filter",
        ),
    ]
    ranked = rank_columns_by_keywords(
        rows,
        ["参与人"],
        top_k=2,
        table_names={"sport_activity_qzs_record"},
    )
    assert len(ranked) == 1
    assert ranked[0].column_name == "people_id"


def test_rank_columns_by_keywords():
    rows = [
        IndexableColumnRow(
            column_id=1,
            table_id=1,
            table_name="sport_activity_qzs_record",
            column_name="people_id",
            description_manual="参与人 ID",
            column_comment_auto="用户id",
            alias_json='["参与人","学生"]',
            column_role="dimension",
        ),
        IndexableColumnRow(
            column_id=2,
            table_id=1,
            table_name="sport_activity_qzs_record",
            column_name="sch_id",
            description_manual="学校 ID",
            column_comment_auto=None,
            alias_json=None,
            column_role="filter",
        ),
    ]
    ranked = rank_columns_by_keywords(rows, ["参与人"], top_k=2)
    assert len(ranked) == 1
    assert ranked[0].column_name == "people_id"
    assert ranked[0].recall_mode == "keyword_fallback"


def test_rank_metrics_by_keywords():
    rows = [
        IndexableMetricRow(
            metric_id=1,
            metric_code="participation_count",
            metric_name="参与人数",
            description="去重 people_id",
            formula_text="COUNT(DISTINCT people_id)",
            relevant_tables="sport_activity_qzs_record",
            alias_json='["参与人数"]',
        )
    ]
    ranked = rank_metrics_by_keywords(rows, ["参与人数"], top_k=1)
    assert ranked[0].metric_code == "participation_count"


def test_rank_field_values_by_keywords():
    rows = [
        IndexableFieldValueRow(
            field_value_id=1,
            column_id=10,
            table_name="sport_activity_qzs_record",
            column_name="project_id",
            value_text="1",
            display_label="跳绳",
            alias_json='["跳绳"]',
        )
    ]
    ranked = rank_field_values_by_keywords(rows, ["跳绳"], top_k=1)
    assert ranked[0].value_text == "1"


def test_expand_tables_after_filter():
    from app.agent.context_builder import expand_table_names_by_relations
    from app.meta.repository import RelationRow

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
    assert "base_student" in expanded


def test_filter_metrics_keeps_top():
    recall = HybridRecallResult(
        keywords=["参与"],
        metrics=[
            RecalledMetric(
                metric_id=1,
                metric_code="a",
                metric_name="A",
                search_text="a",
                score=1.0,
                recall_mode="keyword_fallback",
            ),
            RecalledMetric(
                metric_id=2,
                metric_code="b",
                metric_name="B",
                search_text="b",
                score=5.0,
                recall_mode="keyword_fallback",
            ),
        ],
    )
    merged = merge_retrieved_info(recall)
    merged = filter_metrics(merged, top_n=1)
    assert len(merged.metrics) == 1
    assert merged.metrics[0].metric_code == "b"


def test_route_correct_sql_on_validation_error():
    state = {
        "error_code": "TABLE_NOT_ALLOWED",
        "matched": None,
        "correct_sql_count": 0,
    }
    assert route_after_validate(state) == "correct_sql"


def test_route_format_after_correct_exhausted():
    state = {
        "error_code": "TABLE_NOT_ALLOWED",
        "matched": None,
        "correct_sql_count": 1,
    }
    assert route_after_validate(state) == "format_answer"
