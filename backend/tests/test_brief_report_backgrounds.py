"""Brief Report 背景图路径安全。"""

from app.brief_report.backgrounds import list_backgrounds, resolve_background_path


def test_resolve_background_rejects_traversal():
    assert resolve_background_path("../etc/passwd") is None
    assert resolve_background_path("cover/../../secret.jpg") is None


def test_list_backgrounds_includes_cover_sample():
    data = list_backgrounds()
    assert "cover" in data
    assert "ending" in data
    if data["cover"]:
        first = data["cover"][0]
        assert first["path"].startswith("cover/")
        assert resolve_background_path(first["path"]) is not None
