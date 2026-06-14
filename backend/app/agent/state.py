"""
LangGraph 问数图状态定义。
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.agent.context_builder import MergedRecallContext
from app.ask.models import MatchedQuery
from app.memory.models import SessionMemory, UserPreferenceItem
from app.retrieval.hybrid import RecalledColumn, RecalledFieldValue, RecalledMetric, RecalledTable


class AskGraphState(TypedDict, total=False):
    """单次 /ask 在图中的状态（进程内传递，不做持久化 checkpoint）。"""

    trace_id: str
    question: str
    normalized_question: str
    session_memory: SessionMemory | None
    user_preferences: list[UserPreferenceItem]
    memory_prompt_text: str
    reference_hint: str | None
    memory_skipped: bool
    keywords: list[str]
    recall_mode: str
    recall_tables: list[RecalledTable]
    recall_columns: list[RecalledColumn]
    recall_metrics: list[RecalledMetric]
    recall_field_values: list[RecalledFieldValue]
    merged_recall: MergedRecallContext | None
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
    correct_sql_count: int
    validation_error: str | None
    latency_ms_sql_gen: int | None
    latency_ms_sql_exec: int | None
    token_in: int | None
    token_out: int | None
    value_column: str
    answer_template: str
    # 第 7 周 Agent Plan（§11.7.5）
    plan: dict | None
    plan_skipped: bool
    agent_steps: list[dict]
    tool_observations: list[dict]
    schema_cache: dict[str, dict]
    # 第 8 周 Agent Loop + 分步 SQL
    agent_step_count: int
    agent_loop_done: bool
    sql_steps: list[dict]
    use_agent_path: bool
    # 分步 SQL 执行（多 SQL 路径）
    intermediate_results: list[dict]
    sql_exec_step_index: int
    assembly_mode: str | None
    # 第 9 周语义验证
    verify_passed: bool
    verify_result: dict | None
    verify_attempts: int
    # 第 11～12 周代码召回
    recall_code_artifacts: list
