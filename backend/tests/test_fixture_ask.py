"""Fixture 问句匹配单测（无需 DB）。"""

from app.demo import fixture_ask


def test_normalize_whitespace():
    assert fixture_ask._normalize("  How   many  ") == "how many"


def test_match_english_and_zh(monkeypatch, tmp_path):
    demo = tmp_path / "demo" / "profiles" / "_shared"
    demo.mkdir(parents=True)
    qpath = demo / "questions.json"
    qpath.write_text(
        '{"questions":[{"id":"q1","text":"How many orders are there?",'
        '"text_zh":"一共有多少订单？","sql":"SELECT 1"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(fixture_ask, "_questions_path", lambda _s: qpath)

    class _S:
        demo_root = str(tmp_path)

    hit = fixture_ask.match_fixture("How many orders are there?", _S())
    assert hit is not None and hit["id"] == "q1"
    hit_zh = fixture_ask.match_fixture("一共有多少订单？", _S())
    assert hit_zh is not None
