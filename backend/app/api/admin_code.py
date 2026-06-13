"""
Git 代码知识库管理 HTTP 接口（仅 ADMIN · §11.8.5）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.code.exceptions import CodeKnowledgeError
from app.code.models import CodeArtifactRow, GitRepoRow
from app.code.repository import CodeKnowledgeRepository
from app.code.sync_worker import GitSyncWorker
from app.core.context import UserContext
from app.core.security import require_admin
from app.db.copilot import get_copilot_session
from app.meta.index_service import MetaKnowledgeService
from app.schemas.code import (
    CodeArtifactListResponse,
    CodeArtifactResponse,
    CreateGitRepoRequest,
    GitRepoListResponse,
    GitRepoResponse,
    RebuildCodeIndexResponse,
    RepoSyncStatusResponse,
    SyncRepoResponse,
    UpdateGitRepoRequest,
)
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/admin/code", tags=["admin-code"])


def _repo_response(row: GitRepoRow) -> GitRepoResponse:
    return GitRepoResponse(
        id=row.id,
        name=row.name,
        repoUrl=row.repo_url,
        branch=row.branch,
        authSecretRef=row.auth_secret_ref,
        includePathsJson=row.include_paths_json,
        excludePathsJson=row.exclude_paths_json,
        localPath=row.local_path,
        lastSyncAt=row.last_sync_at.isoformat() if row.last_sync_at else None,
        syncStatus=row.sync_status,
        syncMessage=row.sync_message,
        contentHash=row.content_hash,
        status=row.status,
    )


def _artifact_response(row: CodeArtifactRow) -> CodeArtifactResponse:
    return CodeArtifactResponse(
        id=row.id,
        repoId=row.repo_id,
        artifactType=row.artifact_type,
        title=row.title,
        summaryText=row.summary_text,
        tablesJson=row.tables_json,
        status=row.status,
    )


@router.get("/repos", response_model=GitRepoListResponse, response_model_by_alias=True)
async def list_repos(
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> GitRepoListResponse:
    """列出 Git 仓库配置。"""
    repo = CodeKnowledgeRepository(copilot)
    rows = await repo.list_repos()
    items = [_repo_response(r) for r in rows]
    return GitRepoListResponse(items=items, total=len(items))


@router.post("/repos", response_model=GitRepoResponse, response_model_by_alias=True)
async def create_repo(
    body: CreateGitRepoRequest,
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> GitRepoResponse:
    """新增 Git 仓库配置。"""
    repo = CodeKnowledgeRepository(copilot)
    repo_id = await repo.create_repo(
        name=body.name,
        repo_url=body.repo_url,
        branch=body.branch,
        auth_secret_ref=body.auth_secret_ref,
        include_paths_json=body.include_paths_json,
        exclude_paths_json=body.exclude_paths_json,
        local_path=body.local_path,
    )
    row = await repo.find_repo(repo_id)
    if row is None:
        raise CodeKnowledgeError("CREATE_FAILED", "创建仓库失败", 500)
    return _repo_response(row)


@router.put("/repos/{repo_id}", response_model=GitRepoResponse, response_model_by_alias=True)
async def update_repo(
    repo_id: int,
    body: UpdateGitRepoRequest,
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> GitRepoResponse:
    """更新 Git 仓库配置。"""
    repo = CodeKnowledgeRepository(copilot)
    if await repo.find_repo(repo_id) is None:
        raise CodeKnowledgeError("REPO_NOT_FOUND", "仓库不存在", 404)
    fields = body.model_dump(exclude_unset=True, by_alias=False)
    await repo.update_repo(repo_id, **fields)
    row = await repo.find_repo(repo_id)
    assert row is not None
    return _repo_response(row)


@router.delete("/repos/{repo_id}", status_code=204)
async def delete_repo(
    repo_id: int,
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> None:
    """逻辑删除 Git 仓库。"""
    repo = CodeKnowledgeRepository(copilot)
    if await repo.find_repo(repo_id) is None:
        raise CodeKnowledgeError("REPO_NOT_FOUND", "仓库不存在", 404)
    await repo.delete_repo(repo_id)


@router.post("/repos/{repo_id}/sync", response_model=SyncRepoResponse)
async def sync_repo(
    repo_id: int,
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SyncRepoResponse:
    """触发 Git clone/pull + 解析入库。"""
    worker = GitSyncWorker(copilot, settings)
    result = await worker.sync_repo(repo_id)
    return SyncRepoResponse(**result)


@router.get("/repos/{repo_id}/status", response_model=RepoSyncStatusResponse, response_model_by_alias=True)
async def repo_status(
    repo_id: int,
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
) -> RepoSyncStatusResponse:
    """最近 sync 状态与 symbol/artifact 计数。"""
    repo = CodeKnowledgeRepository(copilot)
    row = await repo.find_repo(repo_id)
    if row is None:
        raise CodeKnowledgeError("REPO_NOT_FOUND", "仓库不存在", 404)
    stats = await repo.count_repo_stats(repo_id)
    return RepoSyncStatusResponse(
        repoId=repo_id,
        syncStatus=row.sync_status,
        syncMessage=row.sync_message,
        symbols=stats.get("symbols", 0),
        artifacts=stats.get("artifacts", 0),
        lastSyncAt=row.last_sync_at.isoformat() if row.last_sync_at else None,
    )


@router.post("/rebuild-index", response_model=RebuildCodeIndexResponse, response_model_by_alias=True)
async def rebuild_code_index(
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RebuildCodeIndexResponse:
    """artifact → ES copilot_ask_code_artifact 全量重建。"""
    svc = MetaKnowledgeService(copilot, settings)
    try:
        count = await svc.rebuild_code_index()
        return RebuildCodeIndexResponse(codeArtifacts=count)
    finally:
        await svc.close()


@router.get("/artifacts", response_model=CodeArtifactListResponse, response_model_by_alias=True)
async def list_artifacts(
    _: Annotated[UserContext, Depends(require_admin)],
    copilot: Annotated[AsyncSession, Depends(get_copilot_session)],
    repo_id: int | None = Query(default=None, alias="repoId"),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CodeArtifactListResponse:
    """运营审核：artifact 列表/搜索。"""
    repo = CodeKnowledgeRepository(copilot)
    rows = await repo.list_artifacts(repo_id=repo_id, q=q, limit=limit)
    items = [_artifact_response(r) for r in rows]
    return CodeArtifactListResponse(items=items, total=len(items))
