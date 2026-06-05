"""混合召回与多阶段上下文单测（无需 ES）。"""

from app.agent.context_builder import filter_metrics, filter_tables, merge_retrieved_info
from app.agent.nodes import route_after_validate
from app.meta.repository import IndexableColumnRow, IndexableFieldValueRow, IndexableMetricRow
from app.retrieval.hybrid import (
    HybridRecallResult,
    RecalledColumn,
    RecalledMetric,
    rank_columns_by_keywords,
    rank_field_values_by_keywords,
    rank_metrics_by_keywords,
)
from app.retrieval.keyword_extractor import extract_keywords


def test_extract_keywords_chinese():
    kws = extract_keywords("本校本月跳绳活动参与人数是多少？")
    assert any("跳绳" in k for k in kws)
    assert any("参与" in k for k in kws)


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


def test_filter_tables_from_recall():
    recall = HybridRecallResult(
        keywords=["参与"],
        columns=[
            RecalledColumn(
                column_id=1,
                table_id=1,
                table_name="sport_activity_qzs_record",
                column_name="people_id",
                search_text="参与人",
                score=3.0,
                recall_mode="keyword_fallback",
            )
        ],
        metrics=[],
        field_values=[],
    )
    merged = merge_retrieved_info(recall)
    merged = filter_tables(merged, top_n=3)
    assert "sport_activity_qzs_record" in merged.table_names


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
