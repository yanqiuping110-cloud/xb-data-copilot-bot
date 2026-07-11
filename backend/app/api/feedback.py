"""
问数反馈：用户点赞/点踩、运营标记 badcase。
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.exceptions import AskError
from app.core.context import UserContext, UserRole
from app.core.security import get_current_user, require_meta_manager
from app.db.copilot import get_copilot_session
from app.memory.badcase_l1 import build_l1_draft_from_badcase
from app.meta.exceptions import MetaError
from app.meta.repository import MetaRepository
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.schemas.meta import BadcaseListResponse, BadcaseResponse, SqlExampleResponse

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse, response_model_by_alias=True)
async def submit_feedback(
    body: FeedbackRequest,
    ctx: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> FeedbackResponse:
    """提交问数反馈；本人 trace 或运营/超管可写。"""
    if body.feedback and body.feedback not in ("up", "down"):
        raise AskError("INVALID_FEEDBACK", "feedback 仅支持 up 或 down", 400)

    result = await session.execute(
        text(
            """
            SELECT user_id, user_feedback, is_badcase, human_corrected_sql
            FROM copilot_ask_turn
            WHERE trace_id = :trace_id AND deleted = 0
            """
        ),
        {"trace_id": body.trace_id},
    )
    row = result.mappings().first()
    if row is None:
        raise AskError("TRACE_NOT_FOUND", "问数记录不存在", 404)

    owner_id = int(row["user_id"])
    is_manager = ctx.role in (UserRole.ADMIN, UserRole.OPERATOR)
    if owner_id != ctx.user_id and not is_manager:
        raise AskError("FORBIDDEN", "无权反馈该问数记录", 403)

    feedback = body.feedback if body.feedback is not None else row.get("user_feedback")
    is_badcase = (
        int(body.is_badcase)
        if body.is_badcase is not None
        else int(row.get("is_badcase") or 0)
    )
    corrected = (
        body.corrected_sql
        if body.corrected_sql is not None
        else row.get("human_corrected_sql")
    )

    await session.execute(
        text(
            """
            UPDATE copilot_ask_turn SET
                user_feedback = :user_feedback,
                is_badcase = :is_badcase,
                human_corrected_sql = :human_corrected_sql
            WHERE trace_id = :trace_id AND deleted = 0
            """
        ),
        {
            "trace_id": body.trace_id,
            "user_feedback": feedback,
            "is_badcase": is_badcase,
            "human_corrected_sql": corrected,
        },
    )
    await session.commit()

    return FeedbackResponse(
        trace_id=body.trace_id,
        user_feedback=feedback,
        is_badcase=bool(is_badcase),
        human_corrected_sql=corrected,
    )


@router.get(
    "/admin/badcases",
    response_model=BadcaseListResponse,
    response_model_by_alias=True,
)
async def list_badcases(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> BadcaseListResponse:
    """运营/超管查看 badcase 与点踩记录。"""
    repo = MetaRepository(session)
    rows = await repo.list_badcases(limit=limit, offset=offset)
    items = [
        BadcaseResponse(
            trace_id=r.trace_id,
            question=r.question,
            final_sql=r.final_sql,
            status=r.status,
            user_feedback=r.user_feedback,
            is_badcase=bool(r.is_badcase),
            human_corrected_sql=r.human_corrected_sql,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
    return BadcaseListResponse(items=items, total=len(items))


@router.post(
    "/admin/badcases/{trace_id}/draft-sql-example",
    response_model=SqlExampleResponse,
    response_model_by_alias=True,
)
async def badcase_to_sql_example_draft(
    trace_id: str,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> SqlExampleResponse:
    """
    将 badcase 一键转为 L1 样例草稿（meta_json.draft=true，不参与匹配）。

    运营在 L1 样例页调低优先级并去掉 draft 后发布。
    """
    repo = MetaRepository(session)
    row = await repo.get_turn_by_trace(trace_id)
    if row is None:
        raise AskError("TRACE_NOT_FOUND", "问数记录不存在", 404)
    if not (row.is_badcase or row.user_feedback == "down"):
        raise AskError("NOT_BADCASE", "仅 badcase 或点踩记录可转 L1 草稿", 400)

    sql_text = (row.human_corrected_sql or row.final_sql or "").strip()
    if not sql_text:
        raise AskError("NO_SQL", "请先填写修正 SQL 或确保原问数有 SQL", 400)

    try:
        draft = build_l1_draft_from_badcase(
            question=row.question,
            sql_text=sql_text,
            role=row.role,
            trace_id=trace_id,
        )
    except ValueError as exc:
        raise AskError("INVALID_DRAFT", str(exc), 400) from exc

    example_id = await repo.insert_sql_example(
        question_pattern=draft["question_pattern"],
        sql_text=draft["sql_text"],
        meta_json=draft["meta_json"],
        role_scope=draft.get("role_scope"),
        degrade_priority=draft["degrade_priority"],
        source_trace_id=trace_id,
        review_status=0,
    )
    await session.commit()
    created = await repo.get_sql_example(example_id)
    if created is None:
        raise MetaError("CREATE_FAILED", "创建 L1 草稿失败", 500)

    meta = None
    if created.meta_json:
        try:
            meta = json.loads(created.meta_json)
        except json.JSONDecodeError:
            meta = None

    return SqlExampleResponse(
        id=created.id,
        question_pattern=created.question_pattern,
        sql_text=created.sql_text,
        meta_json=meta,
        role_scope=created.role_scope,
        degrade_priority=created.degrade_priority,
    )
