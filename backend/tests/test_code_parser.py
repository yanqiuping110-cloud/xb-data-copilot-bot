"""代码解析器单元测试（第 10 周）。"""

from pathlib import Path

from app.code.parser.java_controller import parse_controller_file
from app.code.parser.java_file import parse_java_file
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


def test_parse_java_file_extracts_service_methods():
    text = (FIXTURES / "ActivityReportService.java").read_text(encoding="utf-8")
    parsed = parse_java_file(text, "service/ActivityReportService.java")
    assert parsed is not None
    assert parsed.class_name == "ActivityReportService"
    assert parsed.is_controller is False
    names = {m.method_name for m in parsed.methods}
    assert "countParticipantsBySchool" in names
    assert "buildGradeProjectPivot" in names
    method = next(m for m in parsed.methods if m.method_name == "countParticipantsBySchool")
    assert "按学校统计参与人数" in (method.doc_comment or "")


def test_parse_java_file_controller_via_unified_parser():
    text = (FIXTURES / "SportActivityNewReportController.java").read_text(encoding="utf-8")
    parsed = parse_java_file(text, "report/SportActivityNewReportController.java")
    assert parsed is not None
    assert parsed.is_controller is True
    assert len(parsed.methods) >= 2


def test_parse_java_file_disambiguates_overloaded_methods():
    text = """
public class Result {
    public Result setCode(int code) { return this; }
    public Result setCode(String code) { return this; }
    public int getCode() { return 0; }
}
"""
    parsed = parse_java_file(text, "Result.java")
    assert parsed is not None
    names = [m.qualified_name for m in parsed.methods]
    assert len(names) == len(set(names))
    assert "Result.setCode#3" in names
    assert "Result.setCode#4" in names
    assert "Result.getCode" in names


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
