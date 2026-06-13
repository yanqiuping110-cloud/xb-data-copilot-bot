"""
Git 仓库同步 CLI（§11.8.2 · 第 10 周）。

用法（backend/ 目录）:
  $env:APP_ENV = "development"
  python scripts/sync_git_repos.py --repo-id 1
  python scripts/sync_git_repos.py --all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.code.repository import CodeKnowledgeRepository
from app.code.sync_worker import GitSyncWorker
from app.db.copilot import get_session_factory
from config.settings import get_settings


async def _run(repo_id: int | None, all_repos: bool, local_only: bool) -> int:
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        repo = CodeKnowledgeRepository(session)
        worker = GitSyncWorker(session, settings)
        ids: list[int] = []
        if all_repos:
            rows = await repo.list_repos()
            ids = [r.id for r in rows]
        elif repo_id is not None:
            ids = [repo_id]
        else:
            print("请指定 --repo-id 或 --all")
            return 1

        ok_count = 0
        for rid in ids:
            result = await worker.sync_repo(rid, use_local_only=local_only)
            if result.get("ok"):
                ok_count += 1
                print(f"[OK] repo={rid} {result.get('message')}")
            else:
                print(f"[FAIL] repo={rid} {result.get('error')}")
        print(f"完成: {ok_count}/{len(ids)}")
        return 0 if ok_count == len(ids) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 Git 业务仓库并解析入库")
    parser.add_argument("--repo-id", type=int, help="指定仓库 id")
    parser.add_argument("--all", action="store_true", help="同步全部已配置仓库")
    parser.add_argument("--local-only", action="store_true", help="仅扫描 local_path，不 git pull")
    args = parser.parse_args()
    return asyncio.run(_run(args.repo_id, args.all, args.local_only))


if __name__ == "__main__":
    sys.exit(main())
