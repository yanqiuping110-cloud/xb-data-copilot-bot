"""
POST /api/v1/ask 请求与响应模型。
"""

from app.schemas.base import CamelModel
from app.schemas.chart import ChartSpec


class AskOptions(CamelModel):
    """问数可选参数。"""

    stream: bool = False


class ClarificationAnswerItem(CamelModel):
    """用户对 AskUserQuestion 单题的作答（下一轮 /ask 可选）。"""

    question_id: str
    option_id: str | None = None
    free_text: str | None = None


class AskRequest(CamelModel):
    """问数请求体（不含 schId/role，防篡改）。"""

    trace_id: str | None = None
    session_id: str | None = None
    question: str
    options: AskOptions | None = None
    clarification_answers: list[ClarificationAnswerItem] | None = None
    clarification_thread_id: str | None = None


class AskCancelRequest(CamelModel):
    """用户主动中断进行中的问数。"""

    trace_id: str


class AskCancelResponse(CamelModel):
    """POST /ask/cancel 响应。"""

    ok: bool
    trace_id: str


class IntermediateSqlResult(CamelModel):
    """分步 SQL 单步执行结果（响应用，行数已截断）。"""

    step_id: int | None = None
    goal: str | None = None
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list] | None = None
    row_count: int | None = None


class ClarificationOption(CamelModel):
    """AskUserQuestion 选项。"""

    id: str
    label: str
    recommended: bool = False


class ClarificationQuestion(CamelModel):
    """AskUserQuestion 单题。"""

    id: str
    prompt: str
    allow_free_text: bool = True
    options: list[ClarificationOption] = []


class ClarificationPayload(CamelModel):
    """兼容扁平字段 + AskUserQuestion 多题结构。"""

    question: str | None = None
    missing_slots: list[str] = []
    options: list[str] | None = None
    partial_question: str | None = None
    title: str | None = None
    reason: str | None = None
    questions: list[ClarificationQuestion] | None = None
    thread_id: str | None = None


class AskResponse(CamelModel):
    """问数成功或降级响应。"""

    trace_id: str
    session_id: str | None = None
    status: str
    degrade_level: int = 0
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list] | None = None
    answer: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    assembly_mode: str | None = None
    intermediate_results: list[IntermediateSqlResult] | None = None
    chart_spec: ChartSpec | None = None
    chart_image_url: str | None = None
    visualization_intent: dict | None = None
    dialogue_act: str | None = None
    clarification: ClarificationPayload | None = None
