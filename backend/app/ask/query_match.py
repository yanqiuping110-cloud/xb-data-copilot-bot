"""
问句匹配编排：优先 copilot_sql_example（L1），未命中再回退硬编码 MVP。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.curated_matcher import match_curated
from app.ask.models import MatchedQuery
from app.ask.mvp_matcher import match_question as match_mvp
from app.ask.semantic_repository import SemanticRepository
from app.core.context import UserContext
from app.policy.role_policy import PolicyError, require_school_scope


async def match_question_async(
    question: str,
    ctx: UserContext,
    copilot_session: AsyncSession,
) -> MatchedQuery | None:
    """异步匹配：先库内样例，再 MVP 兜底。"""
    repo = SemanticRepository(copilot_session)
    examples = await repo.list_sql_examples()
    matched = match_curated(question, ctx, examples)
    if matched is not None:
        return matched

    mvp = match_mvp(question, ctx)
    if mvp is None:
        return None
    # 硬编码路径标记来源，便于观测
    return MatchedQuery(
        sql=mvp.sql,
        params=dict(mvp.params),
        tables=mvp.tables,
        value_column=mvp.value_column,
        answer_template=mvp.answer_template,
        admin_only=mvp.admin_only,
        degrade_level=0,
        match_source="mvp",
    )


def ensure_can_run(matched: MatchedQuery, ctx: UserContext) -> None:
    """学校账户未选校等策略错误在此抛出 PolicyError。"""
    if matched.admin_only and ctx.role.value == "SCHOOL":
        raise PolicyError("QUESTION_FORBIDDEN", "学校账户不能查询全平台数据")
    if ctx.role.value == "SCHOOL" and "sch_id" in matched.sql.lower():
        sch_id = require_school_scope(ctx)
        matched.params["sch_id"] = sch_id
