"""Research SSE 帧单测。"""

import json

from app.research import streaming as rs
from app.research.service import wants_stream
from app.schemas.research import ResearchOptions, ResearchReportRequest


def test_wants_stream():
    assert not wants_stream(ResearchReportRequest(request_text="x"))
    assert not wants_stream(
        ResearchReportRequest(request_text="x", options=ResearchOptions(stream=False))
    )
    assert wants_stream(
        ResearchReportRequest(request_text="x", options=ResearchOptions(stream=True))
    )


def test_report_started_event():
    frame = rs.report_started_event("rpt-abc", "标题")
    assert frame.startswith("event: report_started\n")
    data_line = [ln for ln in frame.split("\n") if ln.startswith("data:")][0]
    payload = json.loads(data_line[5:].strip())
    assert payload["reportId"] == "rpt-abc"
    assert payload["title"] == "标题"


def test_pdf_ready_event():
    frame = rs.pdf_ready_event("/api/v1/research/report/rpt-1/pdf", 25, 102400)
    assert "pdf_ready" in frame
    data_line = [ln for ln in frame.split("\n") if ln.startswith("data:")][0]
    payload = json.loads(data_line[5:].strip())
    assert payload["pageCount"] == 25
    assert payload["fileSizeBytes"] == 102400
