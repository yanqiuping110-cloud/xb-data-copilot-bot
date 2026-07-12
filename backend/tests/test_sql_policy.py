"""双库 SQL 策略单元测试。"""

import pytest
from sqlalchemy import text

from app.db.sql_policy import (
    BusinessWriteForbiddenError,
    CopilotDdlForbiddenError,
    assert_business_readonly_sql,
    assert_copilot_no_ddl,
    is_ddl_statement,
    is_dml_statement,
)


def test_business_rejects_insert():
    with pytest.raises(BusinessWriteForbiddenError) as exc:
        assert_business_readonly_sql("INSERT INTO t VALUES (1)")
    assert exc.value.code == "BUSINESS_DML_FORBIDDEN"


def test_business_rejects_alter():
    with pytest.raises(BusinessWriteForbiddenError) as exc:
        assert_business_readonly_sql("ALTER TABLE t ADD COLUMN x INT")
    assert exc.value.code == "BUSINESS_DDL_FORBIDDEN"


def test_business_allows_select():
    assert_business_readonly_sql("SELECT 1")


def test_business_allows_with_select():
    assert_business_readonly_sql(
        "WITH daily AS (SELECT DATE(created_at) AS d FROM sport_order GROUP BY 1) "
        "SELECT * FROM daily"
    )


def test_business_rejects_with_insert_cte():
    with pytest.raises(BusinessWriteForbiddenError) as exc:
        assert_business_readonly_sql(
            "WITH x AS (INSERT INTO t VALUES (1)) SELECT 1"
        )
    assert exc.value.code == "BUSINESS_DML_FORBIDDEN"


def test_copilot_rejects_create_table():
    with pytest.raises(CopilotDdlForbiddenError) as exc:
        assert_copilot_no_ddl("CREATE TABLE x (id INT)")
    assert exc.value.code == "COPILOT_DDL_FORBIDDEN"


def test_copilot_allows_insert():
    from app.db.sql_policy import assert_copilot_no_physical_delete

    assert_copilot_no_physical_delete("INSERT INTO copilot_sys_user (username) VALUES ('a')")


def test_copilot_rejects_delete():
    from app.db.sql_policy import CopilotPhysicalDeleteForbiddenError, assert_copilot_no_physical_delete

    with pytest.raises(CopilotPhysicalDeleteForbiddenError) as exc:
        assert_copilot_no_physical_delete("DELETE FROM copilot_sys_user WHERE id = 1")
    assert exc.value.code == "COPILOT_DELETE_FORBIDDEN"


def test_copilot_allows_metric_column_soft_replace():
    from app.db.sql_policy import assert_copilot_runtime_sql

    assert_copilot_runtime_sql(
        "UPDATE copilot_metric_column SET deleted = 1 WHERE metric_id = 1 AND deleted = 0"
    )
    assert_copilot_runtime_sql(
        """
        INSERT INTO copilot_metric_column (metric_id, column_id, usage_type, deleted)
        VALUES (1, 2, 'measure', 0)
        ON DUPLICATE KEY UPDATE deleted = 0, usage_type = VALUES(usage_type)
        """
    )


def test_is_dml_and_ddl():
    assert is_dml_statement("UPDATE t SET a=1")
    assert is_ddl_statement("DROP TABLE t")
    assert not is_ddl_statement("SELECT * FROM t")


@pytest.mark.asyncio
async def test_copilot_engine_blocks_ddl_at_runtime():
    """问数库引擎钩子应拦截 CREATE TABLE。"""
    from app.db.copilot import get_engine

    engine = get_engine()
    with pytest.raises(RuntimeError, match="COPILOT_DDL_FORBIDDEN"):
        async with engine.connect() as conn:
            await conn.execute(text("CREATE TABLE IF NOT EXISTS copilot_policy_test (id INT)"))
