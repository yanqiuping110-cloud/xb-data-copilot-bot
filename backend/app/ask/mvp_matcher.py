"""
MVP 硬编码问句匹配（已废弃）。

问数链路已改为 L1 样例软参考 + LLM 生成；保留本模块仅为兼容旧 import。
"""

from __future__ import annotations

from app.ask.models import MatchedQuery
from app.core.context import UserContext


def match_question(question: str, ctx: UserContext) -> MatchedQuery | None:
    """不再硬编码 SQL；请维护 copilot_sql_example（L1 样例）。"""
    _ = question, ctx
    return None
