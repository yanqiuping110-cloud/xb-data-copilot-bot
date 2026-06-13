"""代码知识库 API 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GitRepoResponse(BaseModel):
    id: int
    name: str
    repo_url: str = Field(alias="repoUrl")
    branch: str
    auth_secret_ref: str | None = Field(default=None, alias="authSecretRef")
    include_paths_json: str | None = Field(default=None, alias="includePathsJson")
    exclude_paths_json: str | None = Field(default=None, alias="excludePathsJson")
    local_path: str | None = Field(default=None, alias="localPath")
    last_sync_at: str | None = Field(default=None, alias="lastSyncAt")
    sync_status: str = Field(alias="syncStatus")
    sync_message: str | None = Field(default=None, alias="syncMessage")
    content_hash: str | None = Field(default=None, alias="contentHash")
    status: int

    model_config = {"populate_by_name": True}


class GitRepoListResponse(BaseModel):
    items: list[GitRepoResponse]
    total: int


class CreateGitRepoRequest(BaseModel):
    name: str
    repo_url: str = Field(alias="repoUrl")
    branch: str = "main"
    auth_secret_ref: str | None = Field(default=None, alias="authSecretRef")
    include_paths_json: str | None = Field(default=None, alias="includePathsJson")
    exclude_paths_json: str | None = Field(default=None, alias="excludePathsJson")
    local_path: str | None = Field(default=None, alias="localPath")

    model_config = {"populate_by_name": True}


class UpdateGitRepoRequest(BaseModel):
    name: str | None = None
    repo_url: str | None = Field(default=None, alias="repoUrl")
    branch: str | None = None
    auth_secret_ref: str | None = Field(default=None, alias="authSecretRef")
    include_paths_json: str | None = Field(default=None, alias="includePathsJson")
    exclude_paths_json: str | None = Field(default=None, alias="excludePathsJson")
    local_path: str | None = Field(default=None, alias="localPath")
    status: int | None = None

    model_config = {"populate_by_name": True}


class RepoSyncStatusResponse(BaseModel):
    repo_id: int = Field(alias="repoId")
    sync_status: str = Field(alias="syncStatus")
    sync_message: str | None = Field(default=None, alias="syncMessage")
    symbols: int
    artifacts: int
    last_sync_at: str | None = Field(default=None, alias="lastSyncAt")

    model_config = {"populate_by_name": True}


class CodeArtifactResponse(BaseModel):
    id: int
    repo_id: int = Field(alias="repoId")
    artifact_type: str = Field(alias="artifactType")
    title: str
    summary_text: str | None = Field(default=None, alias="summaryText")
    tables_json: str | None = Field(default=None, alias="tablesJson")
    status: int

    model_config = {"populate_by_name": True}


class CodeArtifactListResponse(BaseModel):
    items: list[CodeArtifactResponse]
    total: int


class RebuildCodeIndexResponse(BaseModel):
    code_artifacts: int = Field(alias="codeArtifacts")

    model_config = {"populate_by_name": True}


class SyncRepoResponse(BaseModel):
    ok: bool
    message: str | None = None
    error: str | None = None
    symbols: int | None = None
    artifacts: int | None = None
    links: int | None = None
