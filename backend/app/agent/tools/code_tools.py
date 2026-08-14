"""
代码知识 Agent 只读工具（§11.7.2 / §11.8.4 · 第 12 周）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.code.repository import CodeKnowledgeRepository
from app.meta.repository import MetaRepository
from app.retrieval.hybrid import HybridRetriever
from config.settings import Settings

_SNIPPET_MAX = 8000


async def search_code_artifacts(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str,
    keywords: list[str] | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    """ES / MySQL 召回代码 artifact。"""
    if not settings.code_knowledge_enabled:
        return {"count": 0, "artifacts": [], "error": "CODE_KNOWLEDGE_DISABLED"}
    retriever = HybridRetriever(session, settings)
    try:
        items, mode = await retriever.recall_code_artifacts(
            query,
            keywords or [],
            top_k=top_k or settings.recall_top_k_code,
        )
        artifacts = [
            {
                "id": a.artifact_id,
                "title": a.title,
                "artifact_type": a.artifact_type,
                "score": a.score,
                "tables": a.tables,
                "summary_preview": (a.summary_text or "")[:200],
            }
            for a in items
        ]
        return {"count": len(artifacts), "artifacts": artifacts, "recall_mode": mode}
    finally:
        await retriever.close()


async def get_code_artifact(
    session: AsyncSession,
    settings: Settings,
    *,
    artifact_id: int,
) -> dict[str, Any]:
    """读取 artifact 摘要、表/JOIN/过滤提示与 snippet。"""
    repo = CodeKnowledgeRepository(session)
    row = await repo.get_artifact(artifact_id)
    if not row:
        return {"error": "NOT_FOUND", "artifact_id": artifact_id}
    links = await repo.list_table_links(artifact_id)
    snippet = (row.raw_snippet or "")[:_SNIPPET_MAX]
    return {
        "id": row.id,
        "title": row.title,
        "artifact_type": row.artifact_type,
        "summary_text": row.summary_text,
        "tables": _loads_json_list(row.tables_json),
        "join_hints": _loads_json(row.join_hints_json),
        "filter_hints": _loads_json(row.filter_hints_json),
        "dimensions": _loads_json(row.dimensions_json),
        "metrics": _loads_json(row.metrics_json),
        "table_links": [
            {"table_name": lk.table_name, "link_type": lk.link_type, "confidence": lk.confidence}
            for lk in links
        ],
        "raw_snippet": snippet,
    }


async def trace_code_flow(
    session: AsyncSession,
    settings: Settings,
    *,
    symbol_or_path: str,
    repo_id: int | None = None,
) -> dict[str, Any]:
    """Controller→Mapper→表 调用链 BFS。"""
    repo = CodeKnowledgeRepository(session)
    repos = await repo.list_repos()
    if repo_id is None and repos:
        repo_id = repos[0].id
    if repo_id is None:
        return {"error": "NO_REPO", "path": []}

    symbol = await repo.find_symbol_by_name(repo_id, symbol_or_path)
    if not symbol:
        symbol = await repo.find_symbol_by_hint(repo_id, symbol_or_path)
    if not symbol:
        return {"error": "SYMBOL_NOT_FOUND", "symbol_or_path": symbol_or_path}

    path = await repo.trace_edges_bfs(repo_id, symbol.id)
    return {
        "start": {
            "id": symbol.id,
            "qualified_name": symbol.qualified_name,
            "file_path": symbol.file_path,
        },
        "hops": len(path),
        "path": path,
    }


async def link_artifact_to_meta(
    session: AsyncSession,
    settings: Settings,
    *,
    artifact_id: int,
) -> dict[str, Any]:
    """一次返回代码口径 + meta 字段定义。"""
    repo = CodeKnowledgeRepository(session)
    meta = MetaRepository(session)
    artifact = await get_code_artifact(session, settings, artifact_id=artifact_id)
    if artifact.get("error"):
        return artifact

    tables_meta: list[dict[str, Any]] = []
    for table_name in artifact.get("tables") or []:
        table = await meta.find_table_by_name(table_name)
        if not table:
            continue
        cols = await meta.list_recall_columns(table.id)
        tables_meta.append(
            {
                "table_name": table_name,
                "description": table.description_manual or table.table_comment_auto,
                "columns": [
                    {
                        "name": c.column_name,
                        "role": c.column_role,
                        "description": c.description_manual or c.column_comment_auto,
                    }
                    for c in cols[:20]
                ],
            }
        )
    return {"artifact": artifact, "meta_tables": tables_meta}


def _loads_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _loads_json_list(raw: str | None) -> list[str]:
    data = _loads_json(raw)
    if isinstance(data, list):
        return [str(x) for x in data]
    return []
