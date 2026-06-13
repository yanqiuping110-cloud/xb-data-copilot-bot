"""代码解析器单元测试（第 10 周）。"""

from pathlib import Path

from app.code.parser.java_controller import parse_controller_file
from app.code.parser.mybatis_xml import extract_tables_from_sql, parse_mapper_xml

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "code"


def test_parse_controller_extracts_routes():
    text = (FIXTURES / "SportActivityNewReportController.java").read_text(encoding="utf-8")
    parsed = parse_controller_file(text, "report/SportActivityNewReportController.java")
    assert parsed is not None
    assert parsed.class_name == "SportActivityNewReportController"
    assert len(parsed.methods) >= 2
    paths = {m.http_path for m in parsed.methods}
    assert "/api/report/activity/listBySchool" in paths


def test_parse_mapper_extracts_tables():
    text = (FIXTURES / "ActivityReportMapper.xml").read_text(encoding="utf-8")
    parsed = parse_mapper_xml(text, "mapper/ActivityReportMapper.xml")
    assert parsed is not None
    assert len(parsed.selects) == 2
    tables = parsed.selects[0].tables
    assert "sport_activity_qzs_record" in tables
    assert "sport_project" in tables


def test_extract_tables_from_sql():
    sql = "SELECT * FROM foo JOIN bar ON foo.id = bar.fk"
    tables = extract_tables_from_sql(sql)
    assert "foo" in tables
    assert "bar" in tables
