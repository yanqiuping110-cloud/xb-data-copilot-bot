"""Research runner 离线单测（mock sub_ask）。"""

from unittest.mock import AsyncMock

import pytest

from app.core.context import UserContext, UserRole
from app.research.runner import stream_research_report
from app.schemas.research import ResearchOptions, ResearchReportRequest


def _admin_ctx() -> UserContext:
    return UserContext(trace_id="t", user_id=1, username="admin", role=UserRole.ADMIN)


def _mock_section_result(idx: int) -> dict:
    return {
        "section_index": idx,
        "status": "success",
        "answer": f"第{idx}节分析完成，数据正常。",
        "columns": ["指标", "数值"],
        "rows": [["A", "100"], ["B", "200"]],
        "sub_trace_id": f"trace-{idx}",
        "latency_ms": 100,
    }


@pytest.mark.asyncio
async def test_stream_research_report_yields_lifecycle_events(tmp_path, monkeypatch):
    session = AsyncMock()
    session.commit = AsyncMock()

    async def _count_running(*args, **kwargs):
        return 0

    async def _noop(*args, **kwargs):
        pass

    monkeypatch.setattr("app.research.runner.repo.count_running_reports", _count_running)
    monkeypatch.setattr("app.research.runner.repo.create_report", _noop)
    monkeypatch.setattr("app.research.runner.repo.update_report_plan", _noop)
    monkeypatch.setattr("app.research.runner.repo.insert_sections", _noop)
    monkeypatch.setattr("app.research.runner.repo.update_section_result", _noop)
    monkeypatch.setattr("app.research.runner.repo.finish_report", _noop)
    monkeypatch.setattr("app.research.runner.research_audit.log_research_event", _noop)

    async def _fake_run_section_ask(**kwargs):
        return _mock_section_result(kwargs["section_index"])

    monkeypatch.setattr("app.research.runner.run_section_ask", _fake_run_section_ask)

    from config.settings import Settings

    settings = Settings()
    settings.research_storage_dir = str(tmp_path)
    settings.research_max_sections = 4

    body = ResearchReportRequest(
        request_text="本月运营分析",
        template_code="monthly_ops",
        options=ResearchOptions(stream=False),
    )

    events: list[str] = []
    async for frame in stream_research_report(body, _admin_ctx(), session, settings):
        for line in frame.split("\n"):
            if line.startswith("event:"):
                events.append(line[6:].strip())

    assert "report_started" in events
    assert "plan_revealed" in events
    assert "section_start" in events
    assert "section_done" in events
    assert "pdf_ready" in events
    assert "report_done" in events
