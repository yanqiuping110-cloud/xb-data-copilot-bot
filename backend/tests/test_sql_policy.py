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
