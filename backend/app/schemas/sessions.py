"""
对话 Session API 模型。
"""

from app.schemas.base import CamelModel


class SessionItem(CamelModel):
    """对话列表项。"""

    session_id: str
    title: str | None = None
    turn_count: int = 0
    updated_at: str | None = None
    created_at: str | None = None


class SessionListResponse(CamelModel):
    """GET /sessions 响应。"""

    items: list[SessionItem]
    max_per_user: int


class SessionCreateResponse(CamelModel):
    """POST /sessions 响应。"""

    session_id: str


class SessionMessageItem(CamelModel):
    """单条对话消息。"""

    trace_id: str
    question: str
    final_sql: str | None = None
    status: str
    row_count: int | None = None
    answer: str | None = None
    columns: list[str] | None = None
    rows: list[list] | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    created_at: str | None = None


class SessionMessagesResponse(CamelModel):
    """GET /sessions/{id}/messages 响应。"""

    session_id: str
    messages: list[SessionMessageItem]
