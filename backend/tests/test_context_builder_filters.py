"""上下文构建：默认过滤与字段取值 Prompt 单测。"""

from app.agent.context_builder import (
    _build_field_value_filter_lines,
    _format_sql_literal,
)
from app.retrieval.hybrid import RecalledFieldValue
from app.retrieval.keyword_extractor import extract_keywords


def test_format_sql_literal():
    assert _format_sql_literal("1") == "1"
    assert _format_sql_literal("跳绳") == "'跳绳'"
    assert _format_sql_literal("O'Brien") == "'O''Brien'"


def test_build_field_value_filter_lines():
    values = [
        RecalledFieldValue(
            field_value_id=1,
            table_name="sport_activity_qzs_record",
            column_name="project_id",
            value_text="1",
            display_label="跳绳",
            search_text="",
            score=8.7,
            recall_mode="es_fulltext",
        )
    ]
    lines = _build_field_value_filter_lines(values)
    assert len(lines) == 1
    assert "跳绳" in lines[0]
    assert "project_id = 1" in lines[0]
    assert "必须过滤" in lines[0]


def test_extract_keywords_includes_jump_rope():
    question = "我想查询2026年所有学生跳绳的打卡个数汇总数据"
    keywords = extract_keywords(question)
    assert "跳绳" in keywords
