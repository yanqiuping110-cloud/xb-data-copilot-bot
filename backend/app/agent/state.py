"""
LangGraph 问数图状态定义。
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.ask.models import MatchedQuery


class AskGraphState(TypedDict, total=False):
    """单次 /ask 在图中的状态（进程内传递，不做持久化 checkpoint）。"""

    trace_id: str
    question: str
    normalized_question: str
    context_text: str
    matched: MatchedQuery | None
    raw_sql: str | None
    final_sql: str | None
    sql_params: dict[str, Any]
    tables_used: str
    columns: list[str] | None
    rows: list[list] | None
    answer: str | None
    status: str
    error_code: str | None
    error_message: str | None
    degrade_level: int
    retry_count: int
    latency_ms_sql_gen: int | None
    latency_ms_sql_exec: int | None
    token_in: int | None
    token_out: int | None
    value_column: str
    answer_template: str
