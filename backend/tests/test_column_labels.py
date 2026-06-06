"""结果表头本地化单测。"""

from app.agent.context_builder import MergedRecallContext
from app.ask.column_labels import (
    build_column_label_map,
    localize_result_columns,
    wants_english_column_headers,
)
from app.retrieval.hybrid import RecalledColumn, RecalledMetric


def test_wants_english_column_headers():
    assert wants_english_column_headers("请用英文表头展示结果")
    assert wants_english_column_headers("column names in English please")
    assert not wants_english_column_headers("2025和2026年参与人数与时长")


def test_localize_common_aliases():
    cols = localize_result_columns(
        ["year", "total_people", "total_minutes"],
        question="2025和2026年参与人数与时长",
    )
    assert cols == ["年份", "总人数", "总时长(分钟)"]


def test_keep_english_when_requested():
    cols = localize_result_columns(
        ["year", "total_people"],
        question="用英文表头回答",
    )
    assert cols == ["year", "total_people"]


def test_keep_chinese_columns():
    cols = localize_result_columns(["年份", "总人数"], question="统计人数")
    assert cols == ["年份", "总人数"]


def test_metric_and_column_meta_mapping():
    merged = MergedRecallContext(
        keywords=[],
        recall_mode="hybrid",
        metrics=[
            RecalledMetric(
                metric_id=1,
                metric_code="join_cnt",
                metric_name="参与人次",
                search_text="参与人次 join_cnt",
                score=1.0,
                recall_mode="keyword",
            )
        ],
        columns=[
            RecalledColumn(
                column_id=2,
                table_id=1,
                table_name="sport_activity",
                column_name="sport_value",
                search_text="sport_activity.sport_value 运动量",
                score=0.9,
                recall_mode="keyword",
            )
        ],
    )
    mapping = build_column_label_map(["join_cnt", "sport_value"], {"merged_recall": merged})
    assert mapping["join_cnt"] == "参与人次"
    assert mapping["sport_value"] == "运动量"


def test_token_fallback():
    mapping = build_column_label_map(["total_count"], {})
    assert mapping["total_count"] == "总数量"
