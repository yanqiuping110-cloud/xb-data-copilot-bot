"""
问句匹配遗留：硬命中已移除，仅保留策略校验辅助（测试/扩展用）。
"""

from __future__ import annotations

from app.ask.models import MatchedQuery
from app.core.context import UserContext
from app.policy.role_policy import PolicyError, require_school_scope


def ensure_can_run(matched: MatchedQuery, ctx: UserContext) -> None:
    """学校账户未选校等策略错误在此抛出 PolicyError。"""
    if matched.admin_only and ctx.role.value == "SCHOOL":
        raise PolicyError("QUESTION_FORBIDDEN", "学校账户不能查询全平台数据")
    if ctx.role.value == "SCHOOL" and "sch_id" in matched.sql.lower():
        sch_id = require_school_scope(ctx)
        matched.params["sch_id"] = sch_id
