"""LangGraph 路由单元测试。"""

from app.agent.nodes import route_after_execute, route_after_validate
from app.agent.state import AskGraphState


def test_route_format_on_error():
    state: AskGraphState = {"error_code": "LLM_NO_SQL"}
    assert route_after_validate(state) == "format_answer"


def test_route_correct_sql_when_correctable():
    state: AskGraphState = {
        "error_code": "PARSE_ERROR",
        "correct_sql_count": 0,
    }
    assert route_after_validate(state) == "correct_sql"


def test_route_correct_sql_on_exec_error():
    state: AskGraphState = {
        "error_code": "SQL_EXEC_ERROR",
        "correct_sql_count": 0,
        "validation_error": "Column 'create_time' in where clause is ambiguous",
    }
    assert route_after_execute(state) == "correct_sql"


def test_route_correct_sql_second_attempt():
    state: AskGraphState = {
        "error_code": "SQL_EXEC_ERROR",
        "correct_sql_count": 1,
        "validation_error": "still wrong",
    }
    assert route_after_execute(state) == "correct_sql"


def test_route_correct_sql_third_attempt_on_exec_error():
    state: AskGraphState = {
        "error_code": "SQL_EXEC_ERROR",
        "correct_sql_count": 2,
    }
    assert route_after_execute(state) == "correct_sql"


def test_route_verify_after_exec_error_when_correct_exhausted():
    state: AskGraphState = {
        "error_code": "SQL_EXEC_ERROR",
        "correct_sql_count": 3,
    }
    assert route_after_execute(state) == "verify_answer"
