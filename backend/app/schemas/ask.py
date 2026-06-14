"""
POST /api/v1/ask 请求与响应模型。
"""

from app.schemas.base import CamelModel


class AskOptions(CamelModel):
    """问数可选参数。"""

    stream: bool = False


class AskRequest(CamelModel):
    """问数请求体（不含 schId/role，防篡改）。"""

    trace_id: str | None = None
    session_id: str | None = None
    question: str
    options: AskOptions | None = None


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
