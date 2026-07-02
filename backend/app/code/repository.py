"""
Git 代码知识图谱 MySQL 读写（V009 表）。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.code.models import (
    CodeArtifactRow,
    CodeSymbolRow,
    CodeTableLinkRow,
    GitRepoRow,
    IndexableCodeArtifactRow,
)


def _row_git_repo(r) -> GitRepoRow:
    return GitRepoRow(
        id=int(r["id"]),
        name=r["name"],
        repo_url=r["repo_url"],
        branch=r["branch"],
        auth_secret_ref=r.get("auth_secret_ref"),
        include_paths_json=r.get("include_paths_json"),
        exclude_paths_json=r.get("exclude_paths_json"),
        local_path=r.get("local_path"),
        last_sync_at=r.get("last_sync_at"),
        sync_status=r.get("sync_status") or "pending",
        sync_message=r.get("sync_message"),
        content_hash=r.get("content_hash"),
        status=int(r.get("status") or 1),
    )


def _row_artifact(r) -> CodeArtifactRow:
    return CodeArtifactRow(
        id=int(r["id"]),
        repo_id=int(r["repo_id"]),
        symbol_id=int(r["symbol_id"]) if r.get("symbol_id") else None,
        artifact_type=r["artifact_type"],
        title=r["title"],
        summary_text=r.get("summary_text"),
        tables_json=r.get("tables_json"),
        join_hints_json=r.get("join_hints_json"),
        filter_hints_json=r.get("filter_hints_json"),
        dimensions_json=r.get("dimensions_json"),
        metrics_json=r.get("metrics_json"),
        raw_snippet=r.get("raw_snippet"),
        search_text=r.get("search_text"),
        status=int(r.get("status") or 1),
    )


class CodeKnowledgeRepository:
    """copilot 库代码知识表 CRUD。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_repos(self) -> list[GitRepoRow]:
        """列出未删除的 Git 仓库配置。"""
        sql = text(
            """
            SELECT * FROM copilot_git_repo
            WHERE deleted = 0
            ORDER BY id DESC
            """
        )
        result = await self._session.execute(sql)
        return [_row_git_repo(dict(r)) for r in result.mappings()]

    async def find_repo(self, repo_id: int) -> GitRepoRow | None:
        sql = text("SELECT * FROM copilot_git_repo WHERE id = :id AND deleted = 0")
        result = await self._session.execute(sql, {"id": repo_id})
        row = result.mappings().first()
        return _row_git_repo(dict(row)) if row else None

    async def create_repo(
        self,
        *,
        name: str,
        repo_url: str,
        branch: str = "main",
        auth_secret_ref: str | None = None,
        include_paths_json: str | None = None,
        exclude_paths_json: str | None = None,
        local_path: str | None = None,
    ) -> int:
        sql = text(
            """
            INSERT INTO copilot_git_repo
            (name, repo_url, branch, auth_secret_ref, include_paths_json,
             exclude_paths_json, local_path, sync_status, status)
            VALUES
            (:name, :repo_url, :branch, :auth_secret_ref, :include_paths_json,
             :exclude_paths_json, :local_path, 'pending', 1)
            """
        )
        result = await self._session.execute(
            sql,
            {
                "name": name,
                "repo_url": repo_url,
                "branch": branch,
                "auth_secret_ref": auth_secret_ref,
                "include_paths_json": include_paths_json,
                "exclude_paths_json": exclude_paths_json,
                "local_path": local_path,
            },
        )
        await self._session.commit()
        return int(result.lastrowid)

    async def update_repo(self, repo_id: int, **fields: Any) -> None:
        allowed = {
            "name",
            "repo_url",
            "branch",
            "auth_secret_ref",
            "include_paths_json",
            "exclude_paths_json",
            "local_path",
            "status",
        }
        sets = []
        params: dict[str, Any] = {"id": repo_id}
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = :{key}")
                params[key] = value
        if not sets:
            return
        sql = text(f"UPDATE copilot_git_repo SET {', '.join(sets)} WHERE id = :id AND deleted = 0")
        await self._session.execute(sql, params)
        await self._session.commit()

    async def delete_repo(self, repo_id: int) -> None:
        """逻辑删除仓库并清理其 symbol/edge/artifact 图数据。"""
        await self.clear_repo_graph(repo_id)
        sql = text("UPDATE copilot_git_repo SET deleted = 1 WHERE id = :id")
        await self._session.execute(sql, {"id": repo_id})
        await self._session.commit()

    async def update_sync_status(
        self,
        repo_id: int,
        *,
        sync_status: str,
        sync_message: str | None = None,
        content_hash: str | None = None,
        last_sync_at: datetime | None = None,
    ) -> None:
        sql = text(
            """
            UPDATE copilot_git_repo
            SET sync_status = :sync_status,
                sync_message = :sync_message,
                content_hash = :content_hash,
                last_sync_at = COALESCE(:last_sync_at, NOW())
            WHERE id = :id AND deleted = 0
            """
        )
        await self._session.execute(
            sql,
            {
                "id": repo_id,
                "sync_status": sync_status,
                "sync_message": sync_message,
                "content_hash": content_hash,
                "last_sync_at": last_sync_at,
            },
        )
        await self._session.commit()

    async def clear_repo_graph(self, repo_id: int) -> None:
        """同步前清空该仓库 symbol/edge/artifact/link（逻辑删除；symbol 重命名以释放 uk）。"""
        await self._session.execute(
            text(
                """
                UPDATE copilot_code_table_link tl
                INNER JOIN copilot_code_artifact a ON a.id = tl.artifact_id
                SET tl.deleted = 1
                WHERE a.repo_id = :repo_id AND tl.deleted = 0
                """
            ),
            {"repo_id": repo_id},
        )
        for table in ("copilot_code_edge", "copilot_code_artifact"):
            await self._session.execute(
                text(f"UPDATE {table} SET deleted = 1 WHERE repo_id = :repo_id AND deleted = 0"),
                {"repo_id": repo_id},
            )
        await self._session.execute(
            text(
                """
                UPDATE copilot_code_symbol
                SET deleted = 1,
                    qualified_name = CONCAT(qualified_name, '#del#', id)
                WHERE repo_id = :repo_id AND deleted = 0
                """
            ),
            {"repo_id": repo_id},
        )
        await self._session.commit()

    async def insert_symbol(
        self,
        *,
        repo_id: int,
        symbol_kind: str,
        qualified_name: str,
        file_path: str,
        start_line: int = 0,
        end_line: int = 0,
        signature: str | None = None,
        doc_comment: str | None = None,
        http_method: str | None = None,
        http_path: str | None = None,
        commit: bool = True,
    ) -> int:
        sql = text(
            """
            INSERT INTO copilot_code_symbol
            (repo_id, symbol_kind, qualified_name, file_path, start_line, end_line,
             signature, doc_comment, http_method, http_path, status)
            VALUES
            (:repo_id, :symbol_kind, :qualified_name, :file_path, :start_line, :end_line,
             :signature, :doc_comment, :http_method, :http_path, 1)
            """
        )
        result = await self._session.execute(
            sql,
            {
                "repo_id": repo_id,
                "symbol_kind": symbol_kind,
                "qualified_name": qualified_name,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "signature": signature,
                "doc_comment": doc_comment,
                "http_method": http_method,
                "http_path": http_path,
            },
        )
        if commit:
            await self._session.commit()
        return int(result.lastrowid)

    async def insert_edge(
        self,
        *,
        repo_id: int,
        from_symbol_id: int,
        edge_type: str,
        to_symbol_id: int | None = None,
        target_name: str | None = None,
        commit: bool = True,
    ) -> None:
        sql = text(
            """
            INSERT INTO copilot_code_edge
            (repo_id, from_symbol_id, to_symbol_id, edge_type, target_name, status)
            VALUES (:repo_id, :from_symbol_id, :to_symbol_id, :edge_type, :target_name, 1)
            """
        )
        await self._session.execute(
            sql,
            {
                "repo_id": repo_id,
                "from_symbol_id": from_symbol_id,
                "to_symbol_id": to_symbol_id,
                "edge_type": edge_type,
                "target_name": target_name,
            },
        )
        if commit:
            await self._session.commit()

    async def insert_artifact(
        self,
        *,
        repo_id: int,
        symbol_id: int | None,
        artifact_type: str,
        title: str,
        summary_text: str | None = None,
        tables_json: str | None = None,
        join_hints_json: str | None = None,
        filter_hints_json: str | None = None,
        dimensions_json: str | None = None,
        metrics_json: str | None = None,
        raw_snippet: str | None = None,
        search_text: str | None = None,
        commit: bool = True,
    ) -> int:
        sql = text(
            """
            INSERT INTO copilot_code_artifact
            (repo_id, symbol_id, artifact_type, title, summary_text,
             tables_json, join_hints_json, filter_hints_json,
             dimensions_json, metrics_json, raw_snippet, search_text, status)
            VALUES
            (:repo_id, :symbol_id, :artifact_type, :title, :summary_text,
             :tables_json, :join_hints_json, :filter_hints_json,
             :dimensions_json, :metrics_json, :raw_snippet, :search_text, 1)
            """
        )
        result = await self._session.execute(
            sql,
            {
                "repo_id": repo_id,
                "symbol_id": symbol_id,
                "artifact_type": artifact_type,
                "title": title,
                "summary_text": summary_text,
                "tables_json": tables_json,
                "join_hints_json": join_hints_json,
                "filter_hints_json": filter_hints_json,
                "dimensions_json": dimensions_json,
                "metrics_json": metrics_json,
                "raw_snippet": (raw_snippet or "")[:65000],
                "search_text": search_text,
            },
        )
        if commit:
            await self._session.commit()
        return int(result.lastrowid)

    async def insert_table_link(
        self,
        *,
        artifact_id: int,
        table_name: str,
        link_type: str = "primary_fact",
        confidence: float = 1.0,
        commit: bool = True,
    ) -> None:
        sql = text(
            """
            INSERT INTO copilot_code_table_link
            (artifact_id, table_name, link_type, confidence)
            VALUES (:artifact_id, :table_name, :link_type, :confidence)
            """
        )
        await self._session.execute(
            sql,
            {
                "artifact_id": artifact_id,
                "table_name": table_name,
                "link_type": link_type,
                "confidence": confidence,
            },
        )
        if commit:
            await self._session.commit()

    async def flush(self) -> None:
        """提交当前事务中 pending 的写入。"""
        await self._session.commit()

    async def list_registered_table_names(self) -> set[str]:
        """已注册 meta 表名，用于 table_link 对齐。"""
        sql = text(
            "SELECT table_name FROM copilot_table_meta WHERE status = 1 AND deleted = 0"
        )
        result = await self._session.execute(sql)
        return {str(r[0]) for r in result.fetchall()}

    async def get_artifact(self, artifact_id: int) -> CodeArtifactRow | None:
        sql = text(
            "SELECT * FROM copilot_code_artifact WHERE id = :id AND deleted = 0 AND status = 1"
        )
        result = await self._session.execute(sql, {"id": artifact_id})
        row = result.mappings().first()
        return _row_artifact(dict(row)) if row else None

    async def list_artifacts(
        self,
        *,
        repo_id: int | None = None,
        q: str | None = None,
        limit: int = 50,
    ) -> list[CodeArtifactRow]:
        clauses = ["deleted = 0", "status = 1"]
        params: dict[str, Any] = {"limit": limit}
        if repo_id is not None:
            clauses.append("repo_id = :repo_id")
            params["repo_id"] = repo_id
        if q:
            clauses.append("(title LIKE :q OR search_text LIKE :q)")
            params["q"] = f"%{q}%"
        sql = text(
            f"""
            SELECT * FROM copilot_code_artifact
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT :limit
            """
        )
        result = await self._session.execute(sql, params)
        return [_row_artifact(dict(r)) for r in result.mappings()]

    async def list_table_links(self, artifact_id: int) -> list[CodeTableLinkRow]:
        sql = text(
            """
            SELECT * FROM copilot_code_table_link
            WHERE artifact_id = :artifact_id AND deleted = 0
            """
        )
        result = await self._session.execute(sql, {"artifact_id": artifact_id})
        rows: list[CodeTableLinkRow] = []
        for r in result.mappings():
            d = dict(r)
            rows.append(
                CodeTableLinkRow(
                    id=int(d["id"]),
                    artifact_id=int(d["artifact_id"]),
                    table_name=d["table_name"],
                    link_type=d["link_type"],
                    confidence=float(d["confidence"]),
                )
            )
        return rows

    async def count_repo_stats(self, repo_id: int) -> dict[str, int]:
        """symbol / artifact 计数。"""
        stats = {}
        for label, table in (("symbols", "copilot_code_symbol"), ("artifacts", "copilot_code_artifact")):
            sql = text(f"SELECT COUNT(*) FROM {table} WHERE repo_id = :repo_id AND deleted = 0")
            result = await self._session.execute(sql, {"repo_id": repo_id})
            stats[label] = int(result.scalar() or 0)
        return stats

    async def list_indexable_artifacts(self) -> list[IndexableCodeArtifactRow]:
        sql = text(
            """
            SELECT a.id AS artifact_id, a.repo_id, a.artifact_type, a.title, a.summary_text,
                   a.tables_json, a.search_text
            FROM copilot_code_artifact a
            INNER JOIN copilot_git_repo r ON r.id = a.repo_id AND r.deleted = 0
            WHERE a.deleted = 0 AND a.status = 1 AND a.search_text IS NOT NULL
            """
        )
        result = await self._session.execute(sql)
        rows: list[IndexableCodeArtifactRow] = []
        for r in result.mappings():
            d = dict(r)
            rows.append(
                IndexableCodeArtifactRow(
                    artifact_id=int(d["artifact_id"]),
                    repo_id=int(d["repo_id"]),
                    artifact_type=d["artifact_type"],
                    title=d["title"],
                    summary_text=d.get("summary_text"),
                    tables_json=d.get("tables_json"),
                    search_text=d["search_text"] or "",
                )
            )
        return rows

    async def update_artifact_summary(
        self,
        artifact_id: int,
        *,
        summary_text: str,
        dimensions_json: str | None = None,
        search_text: str | None = None,
    ) -> None:
        sql = text(
            """
            UPDATE copilot_code_artifact
            SET summary_text = :summary_text,
                dimensions_json = COALESCE(:dimensions_json, dimensions_json),
                search_text = COALESCE(:search_text, search_text)
            WHERE id = :id AND deleted = 0
            """
        )
        await self._session.execute(
            sql,
            {
                "id": artifact_id,
                "summary_text": summary_text,
                "dimensions_json": dimensions_json,
                "search_text": search_text,
            },
        )
        await self._session.commit()

    async def find_symbol_by_hint(
        self,
        repo_id: int,
        hint: str,
    ) -> CodeSymbolRow | None:
        """按 qualified_name 或 file_path 子串查找符号。"""
        sql = text(
            """
            SELECT * FROM copilot_code_symbol
            WHERE repo_id = :repo_id AND deleted = 0
              AND (qualified_name LIKE :q OR file_path LIKE :q)
            LIMIT 1
            """
        )
        result = await self._session.execute(
            sql, {"repo_id": repo_id, "q": f"%{hint}%"}
        )
        row = result.mappings().first()
        if not row:
            return None
        d = dict(row)
        return CodeSymbolRow(
            id=int(d["id"]),
            repo_id=int(d["repo_id"]),
            symbol_kind=d["symbol_kind"],
            qualified_name=d["qualified_name"],
            file_path=d["file_path"],
            start_line=int(d["start_line"]),
            end_line=int(d["end_line"]),
            signature=d.get("signature"),
            doc_comment=d.get("doc_comment"),
            http_method=d.get("http_method"),
            http_path=d.get("http_path"),
            status=int(d["status"]),
        )

    async def find_symbol_by_name(
        self,
        repo_id: int,
        qualified_name: str,
    ) -> CodeSymbolRow | None:
        sql = text(
            """
            SELECT * FROM copilot_code_symbol
            WHERE repo_id = :repo_id AND qualified_name = :name AND deleted = 0
            LIMIT 1
            """
        )
        result = await self._session.execute(
            sql, {"repo_id": repo_id, "name": qualified_name}
        )
        row = result.mappings().first()
        if not row:
            return None
        d = dict(row)
        return CodeSymbolRow(
            id=int(d["id"]),
            repo_id=int(d["repo_id"]),
            symbol_kind=d["symbol_kind"],
            qualified_name=d["qualified_name"],
            file_path=d["file_path"],
            start_line=int(d["start_line"]),
            end_line=int(d["end_line"]),
            signature=d.get("signature"),
            doc_comment=d.get("doc_comment"),
            http_method=d.get("http_method"),
            http_path=d.get("http_path"),
            status=int(d["status"]),
        )

    async def trace_edges_bfs(
        self,
        repo_id: int,
        start_symbol_id: int,
        *,
        max_hops: int = 6,
    ) -> list[dict[str, Any]]:
        """从符号出发 BFS 追踪 calls/uses_mapper 边。"""
        visited: set[int] = {start_symbol_id}
        frontier = [start_symbol_id]
        path: list[dict[str, Any]] = []
        hops = 0
        while frontier and hops < max_hops:
            next_frontier: list[int] = []
            for sid in frontier:
                sql = text(
                    """
                    SELECT e.edge_type, e.target_name, e.to_symbol_id,
                           s.qualified_name, s.symbol_kind, s.file_path
                    FROM copilot_code_edge e
                    LEFT JOIN copilot_code_symbol s ON s.id = e.to_symbol_id AND s.deleted = 0
                    WHERE e.from_symbol_id = :sid AND e.repo_id = :repo_id AND e.deleted = 0
                    """
                )
                result = await self._session.execute(
                    sql, {"sid": sid, "repo_id": repo_id}
                )
                for r in result.mappings():
                    d = dict(r)
                    step = {
                        "from_symbol_id": sid,
                        "edge_type": d["edge_type"],
                        "target_name": d.get("target_name"),
                        "to_symbol_id": d.get("to_symbol_id"),
                        "qualified_name": d.get("qualified_name"),
                        "symbol_kind": d.get("symbol_kind"),
                        "file_path": d.get("file_path"),
                    }
                    path.append(step)
                    tid = d.get("to_symbol_id")
                    if tid and tid not in visited:
                        visited.add(int(tid))
                        next_frontier.append(int(tid))
            frontier = next_frontier
            hops += 1
        return path

    @staticmethod
    def dumps_json_list(items: list[str]) -> str:
        return json.dumps(items, ensure_ascii=False)
