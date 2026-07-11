"""思考模式 SSE 事件。"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_client import _chat_create_kwargs, thinking_request_body
from app.agent.streaming import thinking_delta_event
from config.settings import Settings


def test_thinking_delta_event_payload():
    frame = thinking_delta_event("分析表结构")
    assert "event: thinking_delta" in frame
    assert '"delta": "分析表结构"' in frame or '"delta":"分析表结构"' in frame


def test_chat_create_kwargs_use_extra_body_not_thinking_kwarg():
    settings = Settings(
        llm_model="deepseek-v4-flash",
        llm_thinking_enabled=True,
        llm_reasoning_effort="high",
    )
    body = thinking_request_body(settings)
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"

    kwargs = _chat_create_kwargs(
        settings,
        [SystemMessage(content="sys"), HumanMessage(content="hi")],
    )
    assert "thinking" not in kwargs
    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert kwargs["extra_body"]["reasoning_effort"] == "high"
