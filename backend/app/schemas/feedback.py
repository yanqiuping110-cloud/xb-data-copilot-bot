"""
用户反馈与 badcase API 模型。
"""

from app.schemas.base import CamelModel


class FeedbackRequest(CamelModel):
    """POST /api/v1/feedback。"""

    trace_id: str
    feedback: str | None = None  # up | down
    is_badcase: bool | None = None
    corrected_sql: str | None = None


class FeedbackResponse(CamelModel):
    trace_id: str
    user_feedback: str | None = None
    is_badcase: bool
    human_corrected_sql: str | None = None
