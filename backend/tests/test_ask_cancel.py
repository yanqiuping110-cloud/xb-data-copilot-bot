"""问数用户中断单测。"""

from app.agent.runner import USER_CANCELLED_MESSAGE, _cancelled_response


def test_cancelled_response_shape():
    resp = _cancelled_response("trace-1", "sess-1", 0.0)
    assert resp.status == "cancelled"
    assert resp.error_code == "USER_CANCELLED"
    assert resp.error_message == USER_CANCELLED_MESSAGE
    assert resp.trace_id == "trace-1"
