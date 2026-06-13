"""LLM SQL 提取单元测试（不调用真实模型）。"""

from app.agent.llm_sql import _extract_sql


def test_extract_sql_from_fence():
    text = "说明\n```sql\nSELECT COUNT(*) AS cnt FROM sport_activity_qzs_record\n```"
    assert "sport_activity_qzs_record" in _extract_sql(text)


def test_extract_sql_plain_select():
    assert _extract_sql("SELECT 1 AS cnt").startswith("SELECT")


def test_extract_sql_with_cte():
    text = (
        "WITH daily AS (SELECT DATE(created_at) AS d, COUNT(*) AS cnt FROM t GROUP BY 1) "
        "SELECT d, cnt FROM daily"
    )
    sql = _extract_sql(text)
    assert sql is not None
    assert sql.upper().startswith("WITH")
    assert "SELECT d, cnt FROM daily" in sql
