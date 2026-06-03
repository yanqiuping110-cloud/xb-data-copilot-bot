"""LLM SQL 提取单元测试（不调用真实模型）。"""

from app.agent.llm_sql import _extract_sql


def test_extract_sql_from_fence():
    text = "说明\n```sql\nSELECT COUNT(*) AS cnt FROM sport_activity_qzs_record\n```"
    assert "sport_activity_qzs_record" in _extract_sql(text)


def test_extract_sql_plain_select():
    assert _extract_sql("SELECT 1 AS cnt").startswith("SELECT")
