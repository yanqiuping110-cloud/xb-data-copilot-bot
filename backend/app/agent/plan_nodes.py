"""
问句规划节点 plan_question（§11.7.3 · 第 7 周雏形）。

流程：
1. L1 高分 → 跳过 Plan，走原 generate_sql
2. 启发式 + LLM 判定 complexity
3. 按 plan.steps 的 needs_tool 执行 MySQL 只读工具并写 span
"""

from __future__ import annotations

import re
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.context_builder import MergedRecallContext
from app.agent.nodes import _cfg, _span
from app.agent.plan_llm import generate_plan_from_llm
from app.agent.state import AskGraphState
from app.ask.example_ranker import rank_curated_examples_for_prompt
from app.ask.semantic_repository import SemanticRepository
from config.settings import Settings

# 复杂问句特征词（启发式，与 LLM 判定互补）
_COMPLEX_HINTS = re.compile(
    r"对比|分别|各项目|各年级|动态|多维|交叉|pivot|按.+统计|按.+汇总|JOIN|关联"
)


def _seed_recall_summary(merged: MergedRecallContext | None) -> str:
    """将种子召回压缩为 plan LLM 输入。"""
    if merged is None:
        return "（无召回）"
    lines = [
        f"召回模式: {merged.recall_mode}",
        f"关键词: {', '.join(merged.keywords) or '（整句）'}",
        f"候选表: {', '.join(merged.table_names[:5]) or '（无）'}",
    ]
    if merged.metrics:
        lines.append(
            "指标: "
            + ", ".join(f"{m.metric_code}({m.score:.2f})" for m in merged.metrics[:3])
        )
    if merged.field_values:
        lines.append(
            "字段取值: "
            + ", ".join(
                f"{v.table_name}.{v.column_name}={v.value_text}"
                for v in merged.field_values[:3]
            )
        )
    return "\n".join(lines)


def assess_complexity_heuristic(
    question: str,
    merged: MergedRecallContext | None,
) -> str:
    """
    启发式判定问句复杂度（low / high）。

    规则：多表召回、复杂特征词、多指标/取值 → high；否则 low。
    """
    q = question.strip()
    table_count = len(merged.table_names) if merged else 0
    metric_count = len(merged.metrics) if merged else 0
    value_count = len(merged.field_values) if merged else 0

    if table_count >= 2 or metric_count >= 2 or value_count >= 2:
        return "high"
    if _COMPLEX_HINTS.search(q):
        return "high"
    if any(kw in q for kw in ("趋势", "对比", "排名", "占比", "人均")):
        return "high"
    return "low"


def _fallback_plan(question: str, merged: MergedRecallContext | None) -> dict[str, Any]:
    """LLM 不可用时的规则 plan（保证复杂问句 ≥2 步）。"""
    complexity = assess_complexity_heuristic(question, merged)
    tables = (merged.table_names if merged else [])[:3]
    if complexity == "low":
        return {
            "complexity": "low",
            "intent": "simple_aggregate",
            "steps": [
                {
                    "id": 1,
                    "goal": "确认事实表与过滤条件",
                    "tables": tables,
                    "needs_tool": ["describe_table", "search_field_values"],
                }
            ],
            "sources": ["meta:recall", "heuristic"],
        }
    steps: list[dict[str, Any]] = [
        {
            "id": 1,
            "goal": "确定事实表与过滤条件",
            "tables": tables,
            "needs_tool": ["describe_table", "search_field_values"],
        },
        {
            "id": 2,
            "goal": "关联维度表并确认 JOIN 路径",
            "tables": tables,
            "needs_tool": ["list_relations", "get_join_path"],
        },
    ]
    if merged and merged.metrics:
        steps.append(
            {
                "id": 3,
                "goal": "确认指标口径",
                "tables": tables,
                "needs_tool": ["search_metrics"],
            }
        )
    return {
        "complexity": "high",
        "intent": "multi_dim_report",
        "steps": steps,
        "sources": ["meta:recall", "heuristic"],
    }


async def _best_l1_score(
    question: str,
    ctx,
    session,
    settings: Settings,
) -> int:
    """当前问句最高 L1 软参考得分。"""
    sem_repo = SemanticRepository(session)
    examples = await sem_repo.list_sql_examples()
    ranked = rank_curated_examples_for_prompt(
        question,
        ctx,
        examples,
        top_k=1,
        min_score=0,
    )
    return ranked[0][1] if ranked else 0


async def plan_question(state: AskGraphState, config: RunnableConfig) -> dict:
    """
    问句规划：判定复杂度、生成 plan、执行 needs_tool 工具。

    L1 高分或 complexity=low 时设置 plan_skipped，后续仍走 generate_sql。
    """
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or state.get("question") or ""
    merged: MergedRecallContext | None = state.get("merged_recall")

    if not settings.agent_plan_enabled:
        await _span(config, "plan_question", t0, "degraded", {"skipped": True, "reason": "disabled"})
        return {"plan_skipped": True, "plan": None}

    l1_score = await _best_l1_score(question, c["ctx"], c["copilot_session"], settings)
    if l1_score >= settings.plan_l1_fast_path_score:
        await _span(
            config,
            "plan_question",
            t0,
            "success",
            {
                "skipped": True,
                "reason": "l1_fast_path",
                "l1_score": l1_score,
                "complexity": "low",
            },
        )
        return {
            "plan_skipped": True,
            "plan": {
                "complexity": "low",
                "intent": "l1_fast_path",
                "steps": [],
                "sources": ["l1:soft_match"],
                "l1_score": l1_score,
            },
            "degrade_level": max(state.get("degrade_level") or 0, 1),
        }

    recall_summary = _seed_recall_summary(merged)
    heuristic = assess_complexity_heuristic(question, merged)
    plan = await generate_plan_from_llm(
        settings=settings,
        question=question,
        recall_summary=recall_summary,
    )
    if plan is None:
        plan = _fallback_plan(question, merged)
    elif heuristic == "high" and plan.get("complexity") == "low":
        plan["complexity"] = "high"
        if len(plan.get("steps") or []) < 2:
            plan = _fallback_plan(question, merged)

    if plan.get("complexity") == "low" and len(plan.get("steps") or []) <= 1:
        await _span(
            config,
            "plan_question",
            t0,
            "success",
            {"skipped": True, "reason": "low_complexity", "plan": plan},
        )
        return {"plan_skipped": True, "plan": plan}

    await _span(
        config,
        "plan_question",
        t0,
        "success",
        {
            "skipped": False,
            "complexity": plan.get("complexity"),
            "intent": plan.get("intent"),
            "step_count": len(plan.get("steps") or []),
            "plan": plan,
        },
    )
    plan = _inject_code_sources(plan, merged)
    return {
        "plan_skipped": False,
        "plan": plan,
        "tool_observations": [],
        "agent_steps": [],
        "agent_step_count": 0,
        "agent_loop_done": False,
        "use_agent_path": True,
    }


def route_after_plan(state: AskGraphState) -> str:
    """plan_question 之后：快路径 generate_sql，复杂问句进 agent_loop。"""
    if state.get("error_code"):
        return "format_answer"
    if state.get("plan_skipped"):
        return "generate_sql"
    return "agent_loop"


def _inject_code_sources(plan: dict[str, Any], merged: MergedRecallContext | None) -> dict[str, Any]:
    """将代码召回 artifact 写入 plan.sources（§11.8.3 · 第 11 周）。"""
    if merged is None or not merged.code_artifacts:
        return plan
    sources = list(plan.get("sources") or [])
    for art in merged.code_artifacts[:3]:
        src = f"code:artifact:{art.artifact_id}"
        if src not in sources:
            sources.append(src)
    plan["sources"] = sources
    steps = plan.get("steps") or []
    if steps and merged.code_artifacts:
        top = merged.code_artifacts[0]
        pivot = None
        dims = getattr(top, "dimensions_json", None)
        if dims:
            pivot = str(dims)[:80]
        if not pivot and top.title:
            pivot = top.title[:40]
        if pivot and not steps[-1].get("pivot_hint"):
            steps[-1]["pivot_hint"] = pivot
        needs = list(steps[-1].get("needs_tool") or [])
        if "search_code_artifacts" not in needs:
            needs.append("search_code_artifacts")
        steps[-1]["needs_tool"] = needs
    plan["steps"] = steps
    return plan
