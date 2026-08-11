"""列名校验与关系扩展单测。"""

import pytest

from app.agent.context_builder import expand_table_names_by_relations
from app.meta.repository import RelationRow
from app.sql.column_guard import validate_sql_columns
from app.sql.guard import SqlGuardError


def _relation(from_table: str, to_table: str) -> RelationRow:
    return RelationRow(
        id=1,
        from_table_id=1,
        from_table_name=from_table,
        from_column="people_id",
        to_table_id=2,
        to_table_name=to_table,
        to_column="id",
        relation_type="logical_join",
        join_hint=f"{from_table}.people_id = {to_table}.id",
        cardinality="n:1",
        status=1,
    )


def test_expand_table_names_by_relations():
    relations = [_relation("sport_activity_qzs_record", "base_student")]
    expanded = expand_table_names_by_relations(
        ["sport_activity_qzs_record"],
        relations,
        max_tables=5,
    )
    assert expanded == ["sport_activity_qzs_record", "base_student"]


def test_reject_hallucinated_columns():
    sql = (
        "SELECT s.student_name AS student_nm, s.enrollment_year AS enroll_year, "
        "COUNT(r.id) AS sport_check_count "
        "FROM base_student AS s "
        "JOIN sport_activity_qzs_record AS r ON s.id = r.people_id "
        "WHERE r.project_id = 1 "
        "GROUP BY s.student_name, s.enrollment_year"
    )
    column_map = {
        "base_student": {"id", "name", "in_year", "status", "study_status"},
        "sport_activity_qzs_record": {"id", "people_id", "project_id", "sport_count", "create_time"},
    }
    with pytest.raises(SqlGuardError) as exc:
        validate_sql_columns(sql, column_map)
    assert exc.value.code == "COLUMN_NOT_FOUND"
    assert "student_name" in exc.value.message


def test_accept_real_columns():
    sql = (
        "SELECT s.name AS student_name, s.in_year AS enrollment_year, "
        "SUM(r.sport_count) AS sport_check_count "
        "FROM base_student AS s "
        "JOIN sport_activity_qzs_record AS r ON s.id = r.people_id "
        "WHERE r.project_id = 1 "
        "GROUP BY s.name, s.in_year"
    )
    column_map = {
        "base_student": {"id", "name", "in_year", "status", "study_status"},
        "sport_activity_qzs_record": {"id", "people_id", "project_id", "sport_count", "create_time"},
    }
    validate_sql_columns(sql, column_map)


def test_accept_select_alias_in_order_by():
    sql = (
        "SELECT DATE(create_time) AS stat_date, COUNT(DISTINCT people_id) AS participant_count "
        "FROM sport_activity_qzs_record "
        "WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
        "GROUP BY DATE(create_time) "
        "ORDER BY stat_date"
    )
    column_map = {
        "sport_activity_qzs_record": {"id", "people_id", "project_id", "create_time"},
    }
    validate_sql_columns(sql, column_map)


def test_accept_chinese_alias_compat():
    """兼容历史中文 AS（部分方言支持）；校验仍应通过。"""
    sql = (
        "SELECT DATE(create_time) AS 日期, COUNT(DISTINCT people_id) AS 参与人数 "
        "FROM sport_activity_qzs_record "
        "WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
        "GROUP BY DATE(create_time) "
        "ORDER BY 日期"
    )
    column_map = {
        "sport_activity_qzs_record": {"id", "people_id", "project_id", "create_time"},
    }
    validate_sql_columns(sql, column_map)


def test_reject_recall_disabled_column():
    """不参与召回的字段不应出现在 SQL 中（column_map 不含该列时拒绝）。"""
    sql = (
        "SELECT DATE(r.create_time) AS stat_day, SUM(r.sport_value) AS total "
        "FROM sport_activity_qzs_time AS r "
        "WHERE r.record_date >= DATE_SUB(CURRENT_DATE, INTERVAL 1 MONTH) "
        "GROUP BY DATE(r.create_time)"
    )
    column_map = {
        "sport_activity_qzs_time": {
            "id",
            "project_id",
            "sport_value",
            "record_date",
            "done_time",
        },
    }
    with pytest.raises(SqlGuardError) as exc:
        validate_sql_columns(sql, column_map)
    assert exc.value.code == "COLUMN_NOT_FOUND"
    assert "create_time" in exc.value.message
