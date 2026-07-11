"""Research repository 单测（mock session）。"""

from unittest.mock import AsyncMock

import pytest

from app.research import repository as repo


@pytest.mark.asyncio
async def test_create_report_executes_insert():
    session = AsyncMock()
    await repo.create_report(
        session,
        report_id="rpt-test001",
        user_id=1,
        title="测试报告",
        request_text="分析意图",
        template_code="monthly_ops",
    )
    assert session.execute.await_count == 1
    sql = str(session.execute.await_args[0][0])
    assert "INSERT INTO copilot_research_report" in sql


@pytest.mark.asyncio
async def test_count_running_reports():
    from unittest.mock import MagicMock

    session = AsyncMock()
    row_mock = MagicMock()
    row_mock.mappings.return_value.first.return_value = {"cnt": 2}
    session.execute = AsyncMock(return_value=row_mock)
    n = await repo.count_running_reports(session, user_id=1)
    assert n == 2


@pytest.mark.asyncio
async def test_mark_report_cancelled():
    session = AsyncMock()
    await repo.mark_report_cancelled(session, report_id="rpt-x")
    sql = str(session.execute.await_args[0][0])
    assert "cancelled" in sql
