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
        "SELECT s.student_name AS 学生名, s.enrollment_year AS 入学年份, COUNT(r.id) AS 运动打卡数 "
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
        "SELECT s.name AS 学生名, s.in_year AS 入学年份, SUM(r.sport_count) AS 运动打卡数 "
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
