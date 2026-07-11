"""LLM Planner 降级单测。"""

import pytest

from app.research.planner_llm import build_research_plan_llm
from config.settings import Settings


@pytest.mark.asyncio
async def test_planner_llm_falls_back_to_template():
    settings = Settings()
    settings.research_llm_planner_enabled = False
    plan = await build_research_plan_llm(
        "本月运营",
        template_code="monthly_ops",
        max_sections=4,
        settings=settings,
    )
    assert len(plan["sections"]) == 4
