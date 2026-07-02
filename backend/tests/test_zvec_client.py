"""Zvec 检索客户端与混合召回辅助单测。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from app.retrieval.zvec_client import AskZvecClient, build_table_name_filter
from config.settings import Settings


@pytest.fixture
def zvec_settings(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="zvec_test_"))
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ZVEC_DATA_DIR", str(tmp))
    monkeypatch.setenv("VECTOR_STORE", "zvec")
    from config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    yield settings, tmp
    get_settings.cache_clear()
    AskZvecClient(settings)._open_handles.clear()
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_build_table_name_filter():
    assert build_table_name_filter(None) is None
    assert build_table_name_filter(set()) is None
    expr = build_table_name_filter({"base_student", "sport_activity"})
    assert "base_student" in expr
    assert "sport_activity" in expr
    assert "in (" in expr


@pytest.mark.asyncio
async def test_zvec_vector_index_roundtrip(zvec_settings):
    settings, _tmp = zvec_settings
    client = AskZvecClient(settings)
    try:
        assert await client.ping() is True
        index = await client.recreate_vector_index("table", 4)
        count = await client.bulk_index(
            index,
            [
                {
                    "table_id": 1,
                    "table_name": "base_student",
                    "search_text": "学生主数据表",
                    "embedding": [1.0, 0.0, 0.0, 0.0],
                },
                {
                    "table_id": 2,
                    "table_name": "sport_activity",
                    "search_text": "活动打卡记录",
                    "embedding": [0.0, 1.0, 0.0, 0.0],
                },
            ],
        )
        assert count == 2
        hits = await client.search_vector(
            "table",
            [0.95, 0.05, 0.0, 0.0],
            top_k=1,
            query_text="学生",
        )
        assert len(hits) == 1
        assert hits[0]["table_name"] == "base_student"
        assert hits[0]["_score"] > 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_zvec_column_filter_and_fulltext(zvec_settings):
    settings, _tmp = zvec_settings
    client = AskZvecClient(settings)
    try:
        col_index = await client.recreate_vector_index("column", 4)
        await client.bulk_index(
            col_index,
            [
                {
                    "column_id": 10,
                    "table_id": 1,
                    "table_name": "base_student",
                    "column_name": "name",
                    "search_text": "学生姓名",
                    "embedding": [1.0, 0.0, 0.0, 0.0],
                },
                {
                    "column_id": 11,
                    "table_id": 2,
                    "table_name": "sport_activity",
                    "column_name": "people_id",
                    "search_text": "参与人",
                    "embedding": [0.0, 1.0, 0.0, 0.0],
                },
            ],
        )
        filtered = await client.search_vector(
            "column",
            [0.9, 0.1, 0.0, 0.0],
            top_k=5,
            query_text="参与",
            filter_expr=build_table_name_filter({"sport_activity"}),
        )
        assert len(filtered) == 1
        assert filtered[0]["column_name"] == "people_id"

        value_index = await client.recreate_value_index("value")
        await client.bulk_index(
            value_index,
            [
                {
                    "field_value_id": 1,
                    "column_id": 99,
                    "table_name": "sport_activity",
                    "column_name": "project_id",
                    "value_text": "1",
                    "display_label": "跳绳",
                    "search_text": "跳绳 项目",
                }
            ],
        )
        fts_hits = await client.search_fulltext("value", "跳绳", top_k=3)
        assert len(fts_hits) == 1
        assert fts_hits[0]["display_label"] == "跳绳"
    finally:
        await client.close()
