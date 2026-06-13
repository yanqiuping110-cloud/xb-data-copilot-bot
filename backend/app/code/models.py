"""
代码知识图谱数据模型（与 V009 DDL 对应）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class GitRepoRow:
    """copilot_git_repo 一行。"""

    id: int
    name: str
    repo_url: str
    branch: str
    auth_secret_ref: str | None
    include_paths_json: str | None
    exclude_paths_json: str | None
    local_path: str | None
    last_sync_at: datetime | None
    sync_status: str
    sync_message: str | None
    content_hash: str | None
    status: int


@dataclass
class CodeSymbolRow:
    """copilot_code_symbol 一行。"""

    id: int
    repo_id: int
    symbol_kind: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str | None
    doc_comment: str | None
    http_method: str | None
    http_path: str | None
    status: int


@dataclass
class CodeArtifactRow:
    """copilot_code_artifact 一行。"""

    id: int
    repo_id: int
    symbol_id: int | None
    artifact_type: str
    title: str
    summary_text: str | None
    tables_json: str | None
    join_hints_json: str | None
    filter_hints_json: str | None
    dimensions_json: str | None
    metrics_json: str | None
    raw_snippet: str | None
    search_text: str | None
    status: int


@dataclass
class CodeTableLinkRow:
    """copilot_code_table_link 一行。"""

    id: int
    artifact_id: int
    table_name: str
    link_type: str
    confidence: float


@dataclass
class IndexableCodeArtifactRow:
    """ES 代码 artifact 索引一行。"""

    artifact_id: int
    repo_id: int
    artifact_type: str
    title: str
    summary_text: str | None
    tables_json: str | None
    search_text: str
