"""Git sync 辅助函数测试。"""

from app.code.sync_worker import _inject_git_token, _resolve_env_secret, is_local_import, resolve_scan_root


def test_inject_git_token_http():
    url = "http://git.example.com/group/repo.git"
    out = _inject_git_token(url, "glpat-secret")
    assert out == "http://oauth2:glpat-secret@git.example.com/group/repo.git"


def test_inject_git_token_https():
    url = "https://git.example.com/group/repo.git"
    out = _inject_git_token(url, "glpat-secret")
    assert out == "https://oauth2:glpat-secret@git.example.com/group/repo.git"


def test_inject_git_token_skips_when_embedded():
    url = "https://user:pass@git.example.com/group/repo.git"
    assert _inject_git_token(url, "ignored") == url


def test_resolve_env_secret_reads_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.development"
    env_file.write_text("GIT_TOKEN=from-file\n", encoding="utf-8")
    monkeypatch.delenv("GIT_TOKEN", raising=False)
    monkeypatch.setattr("app.code.sync_worker._env_file", lambda: str(env_file))
    assert _resolve_env_secret("GIT_TOKEN") == "from-file"


def test_local_import_detect_and_resolve(tmp_path):
    src = tmp_path / "my-project"
    src.mkdir()
    (src / "Foo.java").write_text("public class Foo {}", encoding="utf-8")
    assert is_local_import("local://import", str(src))
    assert resolve_scan_root("local://import", str(src)) == src.resolve()
