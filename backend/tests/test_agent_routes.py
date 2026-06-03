"""LangGraph 路由与上下文检索单元测试。"""

from app.agent.nodes import route_after_match, route_after_validate
from app.agent.state import AskGraphState
from app.ask.models import MatchedQuery


def test_route_skip_llm_when_matched():
    state: AskGraphState = {
        "matched": MatchedQuery(
            sql="SELECT 1",
            tables=("t",),
            value_column="cnt",
            answer_template="ok",
        )
    }
    assert route_after_match(state) == "validate_sql"


def test_route_llm_when_no_match():
    assert route_after_match({}) == "generate_sql"


def test_route_format_on_error():
    state: AskGraphState = {"error_code": "LLM_NO_SQL"}
    assert route_after_match(state) == "format_answer"
    assert route_after_validate(state) == "format_answer"
