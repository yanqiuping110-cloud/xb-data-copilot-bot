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
from app.code.parser import parse_java_file, parse_mapper_xml
from app.code.repository import CodeKnowledgeRepository
from app.core.log_config import get_logger
from config.settings import ROOT_DIR, Settings, _env_file

logger = get_logger("git_sync")

_DEBUG_LOG = Path(__file__).resolve().parents[3] / "debug-fea756.log"


def _agent_debug(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "fea756",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(__import__("time").time() * 1000),
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion


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


def _inject_git_token(repo_url: str, token: str) -> str:
    """GitLab PAT：oauth2:<token>@host（http/https 均支持）。"""
    if "@" in repo_url.split("://", 1)[-1]:
        return repo_url
    cred = f"oauth2:{token}@"
    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://{cred}", 1)
    if repo_url.startswith("http://"):
        return repo_url.replace("http://", f"http://{cred}", 1)
    return repo_url


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run_git(args: list[str], *, env: dict[str, str]) -> None:
    proc = subprocess.run(args, capture_output=True, env=env)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"git 命令失败: {' '.join(args)}")


def _resolve_env_secret(name: str) -> str | None:
    """从进程环境或 backend/.env.{APP_ENV} 读取密钥（Pydantic 不会注入 os.environ）。"""
    if name in os.environ and os.environ[name]:
        return os.environ[name]
    env_path = Path(_env_file())
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        if key.strip() == name:
            return val.strip().strip('"').strip("'") or None
    return None


def _normalize_local_path(raw: str) -> Path:
    """Windows/Unix 本地路径规范化。"""
    text = raw.strip().strip('"').strip("'")
    if text.startswith("file://"):
        text = text.removeprefix("file://")
    return Path(text).expanduser().resolve()


def is_local_import(repo_url: str, local_path: str | None) -> bool:
    """是否为本地目录导入（非 Git 远程拉取）。"""
    if repo_url.startswith("local://"):
        return True
    if local_path and local_path.strip():
        return True
    if repo_url.startswith("file://"):
        return True
    try:
        p = Path(repo_url.strip())
        if p.is_absolute() and p.is_dir():
            return True
        if len(repo_url) >= 2 and repo_url[1] == ":" and p.is_dir():
            return True
    except OSError:
        pass
    return False


def resolve_scan_root(repo_url: str, local_path: str | None) -> Path:
    """解析本地导入的扫描根目录。"""
    if local_path and local_path.strip():
        root = _normalize_local_path(local_path)
    elif repo_url.startswith("file://"):
        root = _normalize_local_path(repo_url)
    elif repo_url.startswith("local://"):
        raise FileNotFoundError("本地导入须填写「项目目录」绝对路径")
    else:
        root = _normalize_local_path(repo_url)
    if not root.is_dir():
        raise FileNotFoundError(f"本地目录不存在或不是文件夹: {root}")
    return root


def _clone_or_pull(repo_url: str, branch: str, dest: Path, auth_secret_ref: str | None) -> None:
    """浅克隆或 pull；dest 已存在则 pull。"""
    # #region agent log
    _agent_debug(
        "E",
        "sync_worker.py:_clone_or_pull",
        "git clone/pull invoked",
        {"repoUrl": repo_url, "branch": branch, "dest": str(dest), "authSecretRef": auth_secret_ref},
    )
    # #endregion
    env = _git_env()
    token = _resolve_env_secret(auth_secret_ref) if auth_secret_ref else None
    if token:
        repo_url = _inject_git_token(repo_url, token)
    elif auth_secret_ref:
        raise RuntimeError(
            f"环境变量「{auth_secret_ref}」在进程环境与 {_env_file()} 中均未找到。"
            "「凭证 env」应填 .env 中的变量名（如 GIT_TOKEN），token 写在 .env 里，不要填 token 本身。"
        )
    elif repo_url.startswith(("http://", "https://")) and "@" not in repo_url.split("://", 1)[-1]:
        raise RuntimeError(
            f"私有仓库需要凭证：在 .env 中设置 token，并在仓库配置「凭证 env」填写变量名"
            f"（当前 auth_secret_ref={auth_secret_ref or '未配置'}）"
        )

    if dest.exists() and (dest / ".git").exists():
        _run_git(["git", "-C", str(dest), "fetch", "origin", branch, "--depth", "1"], env=env)
        _run_git(["git", "-C", str(dest), "reset", "--hard", f"origin/{branch}"], env=env)
        return

    if dest.exists():
        shutil.rmtree(dest)
    _run_git(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(dest)],
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

        local_mode = is_local_import(row.repo_url, row.local_path)
        # #region agent log
        _agent_debug(
            "B,C",
            "sync_worker.py:sync_repo:entry",
            "sync repo loaded",
            {
                "repoId": repo_id,
                "repoUrl": row.repo_url,
                "localPath": row.local_path,
                "branch": row.branch,
                "isLocalImport": local_mode,
                "useLocalOnly": use_local_only,
            },
        )
        # #endregion
        logger.info(
            "git sync start repo_id=%s name=%s mode=%s",
            repo_id,
            row.name,
            "local" if local_mode else "remote",
        )

        includes = _parse_json_list(row.include_paths_json, ["**/*.java", "**/*Mapper.xml"])
        excludes = _parse_json_list(row.exclude_paths_json, ["**/test/**", "**/target/**"])

        await self._repo.update_sync_status(repo_id, sync_status="syncing", sync_message="同步中")
        try:
            if use_local_only or local_mode:
                work_dir = resolve_scan_root(row.repo_url, row.local_path)
                # #region agent log
                _agent_debug(
                    "D",
                    "sync_worker.py:sync_repo:branch",
                    "took local_import branch",
                    {"workDir": str(work_dir)},
                )
                # #endregion
                logger.info("local import scan repo_id=%s path=%s", repo_id, work_dir)
                if row.local_path != str(work_dir):
                    await self._repo.update_repo(repo_id, local_path=str(work_dir))
            elif row.repo_url.startswith("file://") or Path(row.repo_url).is_dir():
                work_dir = _repo_work_dir(self._settings, repo_id)
                # #region agent log
                _agent_debug(
                    "D",
                    "sync_worker.py:sync_repo:branch",
                    "took file_copy branch",
                    {"workDir": str(work_dir), "repoUrl": row.repo_url},
                )
                # #endregion
                src = Path(row.repo_url.removeprefix("file://"))
                if work_dir.exists():
                    shutil.rmtree(work_dir)
                shutil.copytree(src, work_dir)
                await self._repo.update_repo(repo_id, local_path=str(work_dir))
            else:
                work_dir = Path(row.local_path) if row.local_path else _repo_work_dir(self._settings, repo_id)
                # #region agent log
                _agent_debug(
                    "A,E",
                    "sync_worker.py:sync_repo:branch",
                    "took git_clone branch",
                    {"workDir": str(work_dir), "repoUrl": row.repo_url},
                )
                # #endregion
                _clone_or_pull(row.repo_url, row.branch, work_dir, row.auth_secret_ref)
                await self._repo.update_repo(repo_id, local_path=str(work_dir))

            if not work_dir.is_dir():
                raise FileNotFoundError(f"工作目录不存在: {work_dir}")

            await self._repo.clear_repo_graph(repo_id)
            # #region agent log
            _agent_debug(
                "F",
                "sync_worker.py:sync_repo:clear_graph",
                "clear_repo_graph completed (logical delete)",
                {"repoId": repo_id},
            )
            # #endregion
            stats = await self._parse_and_persist(
                repo_id,
                work_dir,
                includes=includes,
                excludes=excludes,
            )
            digest = _content_hash(work_dir)
            msg = f"symbol={stats['symbols']} artifact={stats['artifacts']} link={stats['links']}"
            logger.info("git sync ok repo_id=%s %s", repo_id, msg)
            await self._repo.update_sync_status(
                repo_id,
                sync_status="ok",
                sync_message=msg,
                content_hash=digest,
            )
            return {"ok": True, "message": msg, **stats}
        except Exception as exc:
            logger.warning("git sync fail repo_id=%s error=%s", repo_id, exc)
            await self._repo.update_sync_status(
                repo_id,
                sync_status="fail",
                sync_message=str(exc)[:500],
            )
            return {"ok": False, "error": str(exc)}

    async def _report_parse_progress(
        self,
        repo_id: int,
        *,
        processed: int,
        total: int,
        symbol_count: int,
        artifact_count: int,
        link_count: int,
        flush: bool,
    ) -> None:
        msg = (
            f"解析中 {processed}/{total} 文件 · "
            f"symbol={symbol_count} artifact={artifact_count} link={link_count}"
        )
        logger.info(
            "git sync parse progress repo_id=%s files=%s/%s symbols=%s artifacts=%s links=%s",
            repo_id,
            processed,
            total,
            symbol_count,
            artifact_count,
            link_count,
        )
        # #region agent log
        _agent_debug(
            "J",
            "sync_worker.py:_parse_and_persist:progress",
            "parse progress",
            {
                "repoId": repo_id,
                "processedFiles": processed,
                "totalFiles": total,
                "symbols": symbol_count,
                "artifacts": artifact_count,
                "links": link_count,
            },
        )
        # #endregion
        if flush:
            await self._repo.flush()
        await self._repo.update_sync_status(
            repo_id,
            sync_status="syncing",
            sync_message=msg,
        )

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

        files: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if _match_path(rel, includes, excludes):
                files.append(path)

        total_files = len(files)
        progress_every = 50
        logger.info("git sync parse start repo_id=%s files=%s", repo_id, total_files)
        await self._report_parse_progress(
            repo_id,
            processed=0,
            total=total_files,
            symbol_count=0,
            artifact_count=0,
            link_count=0,
            flush=False,
        )

        for processed, path in enumerate(files, start=1):
            rel = str(path.relative_to(root)).replace("\\", "/")
            text = path.read_text(encoding="utf-8", errors="ignore")
            lower = rel.lower()

            if lower.endswith(".java"):
                parsed = parse_java_file(text, rel)
                if not parsed:
                    continue
                for method in parsed.methods:
                    is_controller = method.http_path is not None
                    sym_id = await self._repo.insert_symbol(
                        repo_id=repo_id,
                        symbol_kind="route" if is_controller else "method",
                        qualified_name=method.qualified_name,
                        file_path=method.file_path,
                        start_line=method.start_line,
                        end_line=method.end_line,
                        signature=method.signature,
                        doc_comment=method.doc_comment,
                        http_method=method.http_method,
                        http_path=method.http_path,
                        commit=False,
                    )
                    symbol_count += 1
                    if is_controller:
                        title = f"{method.http_method} {method.http_path} · {method.method_name}"
                        artifact_type = "controller_method"
                    else:
                        title = f"{method.class_name}.{method.method_name}"
                        artifact_type = "java_method"
                    summary = method.doc_comment or title
                    search_text = build_code_search_text(
                        title=title,
                        summary_text=summary,
                        tables=[],
                        artifact_type=artifact_type,
                    )
                    await self._repo.insert_artifact(
                        repo_id=repo_id,
                        symbol_id=sym_id,
                        artifact_type=artifact_type,
                        title=title,
                        summary_text=summary,
                        tables_json=CodeKnowledgeRepository.dumps_json_list([]),
                        raw_snippet=method.body_snippet,
                        search_text=search_text,
                        commit=False,
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
                        commit=False,
                    )
                    symbol_count += 1
                    for table in sel.tables:
                        await self._repo.insert_edge(
                            repo_id=repo_id,
                            from_symbol_id=sym_id,
                            edge_type="references_table",
                            target_name=table,
                            commit=False,
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
                        commit=False,
                    )
                    artifact_count += 1
                    for table in sel.tables:
                        if table in registered_tables:
                            await self._repo.insert_table_link(
                                artifact_id=art_id,
                                table_name=table,
                                link_type="primary_fact",
                                confidence=1.0,
                                commit=False,
                            )
                            link_count += 1

            if processed % progress_every == 0 or processed == total_files:
                await self._report_parse_progress(
                    repo_id,
                    processed=processed,
                    total=total_files,
                    symbol_count=symbol_count,
                    artifact_count=artifact_count,
                    link_count=link_count,
                    flush=True,
                )

        return {"symbols": symbol_count, "artifacts": artifact_count, "links": link_count}
