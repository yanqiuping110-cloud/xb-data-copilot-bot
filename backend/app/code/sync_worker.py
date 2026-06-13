"""
Git 仓库同步与代码解析入库（§11.8.2 · 第 10 周）。

支持：
- git clone --depth 1 / 本地目录扫描（无 Git 时用于 fixture）
- Java Controller + MyBatis XML 规则解析
- symbol / edge / artifact / table_link 写入 MySQL
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.code.index_text import build_code_search_text
from app.code.parser import parse_controller_file, parse_mapper_xml
from app.code.repository import CodeKnowledgeRepository
from config.settings import ROOT_DIR, Settings


def _parse_json_list(raw: str | None, default: list[str]) -> list[str]:
    if not raw:
        return default
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else default
    except json.JSONDecodeError:
        return default


def _match_path(rel_path: str, includes: list[str], excludes: list[str]) -> bool:
    """路径 glob 过滤。"""
    norm = rel_path.replace("\\", "/")
    if excludes and any(fnmatch(norm, pat) for pat in excludes):
        return False
    if not includes:
        return True
    return any(fnmatch(norm, pat) for pat in includes)


def _repo_work_dir(settings: Settings, repo_id: int) -> Path:
    base = ROOT_DIR / "data" / "repos" / str(repo_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _clone_or_pull(repo_url: str, branch: str, dest: Path, auth_secret_ref: str | None) -> None:
    """浅克隆或 pull；dest 已存在则 pull。"""
    env = os.environ.copy()
    if auth_secret_ref and auth_secret_ref in os.environ:
        token = os.environ[auth_secret_ref]
        if repo_url.startswith("https://") and "@" not in repo_url:
            repo_url = repo_url.replace("https://", f"https://{token}@", 1)

    if dest.exists() and (dest / ".git").exists():
        subprocess.run(
            ["git", "-C", str(dest), "fetch", "origin", branch, "--depth", "1"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(dest), "reset", "--hard", f"origin/{branch}"],
            check=True,
            capture_output=True,
        )
        return

    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(dest)],
        check=True,
        capture_output=True,
        env=env,
    )


def _content_hash(root: Path) -> str:
    """目录内容粗 hash（文件路径+大小）。"""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            rel = str(path.relative_to(root))
            h.update(rel.encode())
            h.update(str(path.stat().st_size).encode())
    return h.hexdigest()[:32]


class GitSyncWorker:
    """单仓库同步 worker。"""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repo = CodeKnowledgeRepository(session)

    async def sync_repo(
        self,
        repo_id: int,
        *,
        use_local_only: bool = False,
    ) -> dict:
        """
        同步指定仓库：拉代码 → 解析 → 入库。

        use_local_only=True 时跳过 git，仅扫描 local_path（测试/fixture 用）。
        """
        row = await self._repo.find_repo(repo_id)
        if not row:
            return {"ok": False, "error": "REPO_NOT_FOUND"}

        work_dir = Path(row.local_path) if row.local_path else _repo_work_dir(self._settings, repo_id)
        includes = _parse_json_list(row.include_paths_json, ["**/*ReportController.java", "**/*Mapper.xml"])
        excludes = _parse_json_list(row.exclude_paths_json, ["**/test/**", "**/target/**"])

        await self._repo.update_sync_status(repo_id, sync_status="syncing", sync_message="同步中")
        try:
            if not use_local_only:
                if row.repo_url.startswith("file://") or Path(row.repo_url).is_dir():
                    src = Path(row.repo_url.removeprefix("file://"))
                    if work_dir.exists():
                        shutil.rmtree(work_dir)
                    shutil.copytree(src, work_dir)
                else:
                    _clone_or_pull(row.repo_url, row.branch, work_dir, row.auth_secret_ref)
                    await self._repo.update_repo(repo_id, local_path=str(work_dir))

            if not work_dir.is_dir():
                raise FileNotFoundError(f"工作目录不存在: {work_dir}")

            await self._repo.clear_repo_graph(repo_id)
            stats = await self._parse_and_persist(
                repo_id,
                work_dir,
                includes=includes,
                excludes=excludes,
            )
            digest = _content_hash(work_dir)
            msg = f"symbol={stats['symbols']} artifact={stats['artifacts']} link={stats['links']}"
            await self._repo.update_sync_status(
                repo_id,
                sync_status="ok",
                sync_message=msg,
                content_hash=digest,
            )
            return {"ok": True, "message": msg, **stats}
        except Exception as exc:
            await self._repo.update_sync_status(
                repo_id,
                sync_status="fail",
                sync_message=str(exc)[:500],
            )
            return {"ok": False, "error": str(exc)}

    async def _parse_and_persist(
        self,
        repo_id: int,
        root: Path,
        *,
        includes: list[str],
        excludes: list[str],
    ) -> dict[str, int]:
        registered_tables = await self._repo.list_registered_table_names()
        symbol_count = 0
        artifact_count = 0
        link_count = 0

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if not _match_path(rel, includes, excludes):
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            lower = rel.lower()

            if lower.endswith(".java") and "controller" in lower:
                parsed = parse_controller_file(text, rel)
                if not parsed:
                    continue
                for method in parsed.methods:
                    sym_id = await self._repo.insert_symbol(
                        repo_id=repo_id,
                        symbol_kind="route",
                        qualified_name=method.qualified_name,
                        file_path=method.file_path,
                        start_line=method.start_line,
                        end_line=method.end_line,
                        signature=method.signature,
                        doc_comment=method.doc_comment,
                        http_method=method.http_method,
                        http_path=method.http_path,
                    )
                    symbol_count += 1
                    title = f"{method.http_method} {method.http_path} · {method.method_name}"
                    summary = method.doc_comment or title
                    search_text = build_code_search_text(
                        title=title,
                        summary_text=summary,
                        tables=[],
                        artifact_type="controller_method",
                    )
                    art_id = await self._repo.insert_artifact(
                        repo_id=repo_id,
                        symbol_id=sym_id,
                        artifact_type="controller_method",
                        title=title,
                        summary_text=summary,
                        tables_json=CodeKnowledgeRepository.dumps_json_list([]),
                        raw_snippet=method.body_snippet,
                        search_text=search_text,
                    )
                    artifact_count += 1

            elif lower.endswith(".xml") and "mapper" in lower:
                parsed = parse_mapper_xml(text, rel)
                if not parsed:
                    continue
                for sel in parsed.selects:
                    sym_id = await self._repo.insert_symbol(
                        repo_id=repo_id,
                        symbol_kind="mapper_statement",
                        qualified_name=sel.qualified_name,
                        file_path=sel.file_path,
                        signature=sel.statement_id,
                        doc_comment=None,
                    )
                    symbol_count += 1
                    for table in sel.tables:
                        await self._repo.insert_edge(
                            repo_id=repo_id,
                            from_symbol_id=sym_id,
                            edge_type="references_table",
                            target_name=table,
                        )
                    title = f"MyBatis {sel.statement_id}"
                    summary = sel.sql_text[:500]
                    search_text = build_code_search_text(
                        title=title,
                        summary_text=summary,
                        tables=sel.tables,
                        artifact_type="mybatis_select",
                    )
                    art_id = await self._repo.insert_artifact(
                        repo_id=repo_id,
                        symbol_id=sym_id,
                        artifact_type="mybatis_select",
                        title=title,
                        summary_text=summary,
                        tables_json=CodeKnowledgeRepository.dumps_json_list(sel.tables),
                        raw_snippet=sel.raw_snippet,
                        search_text=search_text,
                    )
                    artifact_count += 1
                    for table in sel.tables:
                        if table in registered_tables:
                            await self._repo.insert_table_link(
                                artifact_id=art_id,
                                table_name=table,
                                link_type="primary_fact",
                                confidence=1.0,
                            )
                            link_count += 1

        return {"symbols": symbol_count, "artifacts": artifact_count, "links": link_count}
