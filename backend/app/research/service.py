"""Research HTTP 服务入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.research.runner import run_research_report, stream_research_report
from app.schemas.research import ResearchReportRequest, ResearchReportResponse
from config.settings import Settings


def wants_stream(body: ResearchReportRequest) -> bool:
    return bool(body.options and body.options.stream)


async def handle_research_report(
    body: ResearchReportRequest,
    ctx: UserContext,
    session: AsyncSession,
    settings: Settings,
) -> ResearchReportResponse:
    if not settings.research_enabled:
        from app.research.runner import ResearchError

        raise ResearchError("RESEARCH_DISABLED", "深度洞察功能未启用", 503)
    return await run_research_report(body, ctx, session, settings)


async def handle_research_stream(
    body: ResearchReportRequest,
    ctx: UserContext,
    session: AsyncSession,
    settings: Settings,
) -> AsyncIterator[str]:
    if not settings.research_enabled:
        from app.research import streaming as rs

        yield rs.error_event("RESEARCH_DISABLED", "深度洞察功能未启用")
        return
    async for frame in stream_research_report(body, ctx, session, settings):
        yield frame
