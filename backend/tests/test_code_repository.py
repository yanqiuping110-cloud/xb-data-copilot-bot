"""CodeKnowledgeRepository 单元测试。"""

from types import SimpleNamespace

from app.code.repository import _row_git_repo


def test_row_git_repo_accepts_mapping_dict():
    """list_repos 应使用 dict(row)，而非 row._mapping。"""
    row = {
        "id": 1,
        "name": "demo",
        "repo_url": "https://gitlab.example.com/a/b.git",
        "branch": "main",
        "auth_secret_ref": "GIT_TOKEN",
        "include_paths_json": '["**/*.java"]',
        "exclude_paths_json": None,
        "local_path": None,
        "last_sync_at": None,
        "sync_status": "pending",
        "sync_message": None,
        "content_hash": None,
        "status": 1,
    }
    mapped = _row_git_repo(dict(row))
    assert mapped.id == 1
    assert mapped.name == "demo"
    assert mapped.sync_status == "pending"
