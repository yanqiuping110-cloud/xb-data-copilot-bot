"""
Phase 2 运营 API：术语库、L1 发布、运营统计。
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.exceptions import AskError
from app.core.context import UserContext
from app.core.security import require_meta_manager
from app.db.copilot import get_copilot_session
from app.memory.badcase_l1 import build_l1_draft_from_badcase
from app.meta.exceptions import MetaError
from app.meta.glossary_repository import GlossaryRepository
from app.meta.glossary_service import suggest_terms_from_question
from app.meta.repository import MetaRepository
from app.schemas.meta import (
    CreateGlossaryRequest,
    GlossaryListResponse,
    GlossarySuggestResponse,
    GlossaryTermResponse,
    OpsStatsResponse,
    SqlExampleResponse,
    UpdateGlossaryRequest,
)

router = APIRouter(prefix="/api/v1/admin/meta", tags=["admin-ops"])


def _glossary_response(row) -> GlossaryTermResponse:
    return GlossaryTermResponse(
        id=row.id,
        term=row.term,
        canonical_name=row.canonical_name,
        definition=row.definition,
        ref_type=row.ref_type,
        ref_id=row.ref_id,
        scope_role=row.scope_role,
        status=row.status,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


def _sql_example_response(row) -> SqlExampleResponse:
    meta = None
    if row.meta_json:
        try:
            meta = json.loads(row.meta_json)
        except json.JSONDecodeError:
            meta = None
    return SqlExampleResponse(
        id=row.id,
        question_pattern=row.question_pattern,
        sql_text=row.sql_text,
        description=row.description,
        meta_json=meta,
        role_scope=row.role_scope,
        degrade_priority=row.degrade_priority,
        source_trace_id=row.source_trace_id,
        review_status=row.review_status,
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


@router.get("/ops/stats", response_model=OpsStatsResponse, response_model_by_alias=True)
async def ops_stats(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> OpsStatsResponse:
    """运营看板只读统计。"""
    repo = MetaRepository(session)
    stats = await repo.count_ops_stats()
    return OpsStatsResponse(**stats)


@router.get("/glossary", response_model=GlossaryListResponse, response_model_by_alias=True)
async def list_glossary(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
    status: int | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> GlossaryListResponse:
    repo = GlossaryRepository(session)
    rows = await repo.list_terms(status=status, offset=offset, limit=limit)
    items = [_glossary_response(r) for r in rows]
    return GlossaryListResponse(items=items, total=len(items))


@router.post("/glossary", response_model=GlossaryTermResponse, response_model_by_alias=True)
async def create_glossary(
    body: CreateGlossaryRequest,
    ctx: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> GlossaryTermResponse:
    repo = GlossaryRepository(session)
    term_id = await repo.insert_term(
        term=body.term,
        canonical_name=body.canonical_name,
        definition=body.definition,
        ref_type=body.ref_type,
        ref_id=body.ref_id,
        scope_role=body.scope_role,
        status=body.status,
        created_by=ctx.user_id,
    )
    await session.commit()
    row = await repo.get_term(term_id)
    if row is None:
        raise MetaError("CREATE_FAILED", "创建术语失败", 500)
    return _glossary_response(row)


@router.put("/glossary/{term_id}", response_model=GlossaryTermResponse, response_model_by_alias=True)
async def update_glossary(
    term_id: int,
    body: UpdateGlossaryRequest,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> GlossaryTermResponse:
    repo = GlossaryRepository(session)
    existing = await repo.get_term(term_id)
    if existing is None:
        raise MetaError("NOT_FOUND", "术语不存在", 404)
    await repo.update_term(
        term_id,
        term=body.term,
        canonical_name=body.canonical_name,
        definition=body.definition,
        ref_type=body.ref_type,
        ref_id=body.ref_id,
        scope_role=body.scope_role,
        status=body.status,
    )
    await session.commit()
    row = await repo.get_term(term_id)
    assert row is not None
    return _glossary_response(row)


@router.delete("/glossary/{term_id}")
async def delete_glossary(
    term_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> dict:
    repo = GlossaryRepository(session)
    existing = await repo.get_term(term_id)
    if existing is None:
        raise MetaError("NOT_FOUND", "术语不存在", 404)
    await repo.delete_term(term_id)
    await session.commit()
    return {"ok": True}


@router.post(
    "/l1/{example_id}/publish",
    response_model=SqlExampleResponse,
    response_model_by_alias=True,
)
async def publish_l1_example(
    example_id: int,
    ctx: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> SqlExampleResponse:
    """L1 草稿审核发布。"""
    repo = MetaRepository(session)
    row = await repo.get_sql_example(example_id)
    if row is None:
        raise MetaError("NOT_FOUND", "样例不存在", 404)
    try:
        await repo.publish_sql_example(example_id, reviewed_by=ctx.user_id)
    except ValueError as exc:
        raise MetaError("PUBLISH_FAILED", str(exc), 400) from exc
    await session.commit()
    updated = await repo.get_sql_example(example_id)
    if updated is None:
        raise MetaError("PUBLISH_FAILED", "发布失败", 500)
    return _sql_example_response(updated)


@router.post(
    "/badcase/{trace_id}/promote-glossary",
    response_model=GlossarySuggestResponse,
    response_model_by_alias=True,
)
async def promote_glossary_from_badcase(
    trace_id: str,
    ctx: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> GlossarySuggestResponse:
    """从 badcase 问句抽取术语候选并写入草稿（status=0）。"""
    meta_repo = MetaRepository(session)
    row = await meta_repo.get_turn_by_trace(trace_id)
    if row is None:
        raise AskError("TRACE_NOT_FOUND", "问数记录不存在", 404)
    suggestions = suggest_terms_from_question(row.question)
    glossary_repo = GlossaryRepository(session)
    created: list[dict] = []
    for item in suggestions:
        term_id = await glossary_repo.insert_term(
            term=item["term"],
            canonical_name=item["canonicalName"],
            definition=item.get("definition"),
            status=0,
            created_by=ctx.user_id,
        )
        created.append({"id": term_id, **item})
    await session.commit()
    return GlossarySuggestResponse(items=created)


@router.post(
    "/badcase/{trace_id}/promote-l1",
    response_model=SqlExampleResponse,
    response_model_by_alias=True,
)
async def promote_l1_from_badcase(
    trace_id: str,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> SqlExampleResponse:
    """badcase 一键转 L1 草稿。"""
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
    return _sql_example_response(created)
