"""
问句规划节点 plan_question（§11.7.3 · 第 7 周雏形）。

由 Plan LLM 判定 complexity / multi_sql；L1 样例由 select_l1_examples 节点预先精选。
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.context_builder import MergedRecallContext
from app.agent.l1_nodes import _dicts_to_candidates
from app.agent.plan_compare import (
    enrich_sql_steps_from_reference_sql,
    get_sql_execution_steps,
    plan_requires_multi_sql,
)
from app.agent.nodes import _cfg, _span
from app.agent.chart_builder import infer_visualization_from_question, normalize_visualization_intent
from app.agent.plan_llm import generate_plan_from_llm
from app.agent.state import AskGraphState
from app.ask.l1_service import primary_l1_sql
from config.settings import Settings


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


def _fallback_plan() -> dict[str, Any]:
    """LLM 不可用时的最小 plan（单步、不分步 SQL）。"""
    return {
        "complexity": "low",
        "intent": "open_query",
        "multi_sql": False,
        "steps": [
            {
                "id": 1,
                "goal": "生成单条查询 SQL",
                "tables": [],
                "needs_tool": ["describe_table"],
                "sql_step": False,
            }
        ],
        "sources": ["heuristic:fallback"],
    }


def _ensure_plan_visualization(plan: dict[str, Any], question: str) -> dict[str, Any]:
    """补齐 plan.visualization；无 LLM 输出时用问句规则推断。"""
    if not plan.get("visualization"):
        plan["visualization"] = infer_visualization_from_question(question)
    else:
        plan["visualization"] = normalize_visualization_intent(plan["visualization"])
    return plan


async def plan_question(state: AskGraphState, config: RunnableConfig) -> dict:
    """
    问句规划：LLM 判定复杂度、multi_sql、步骤分解。

    complexity=low 且 multi_sql=false 时 plan_skipped，走 generate_sql。
    """
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = (
        state.get("recall_question")
        or state.get("normalized_question")
        or state.get("question")
        or ""
    )
    merged: MergedRecallContext | None = state.get("merged_recall")

    if not settings.agent_plan_enabled:
        intent = infer_visualization_from_question(question)
        await _span(config, "plan_question", t0, "degraded", {"skipped": True, "reason": "disabled"})
        return {"plan_skipped": True, "plan": None, "visualization_intent": intent}

    selected_l1 = _dicts_to_candidates(state.get("selected_l1_examples"))
    l1_sql = primary_l1_sql(selected_l1)
    recall_summary = _seed_recall_summary(merged)
    context_text = state.get("context_text") or ""

    plan = await generate_plan_from_llm(
        settings=settings,
        question=question,
        recall_summary=recall_summary,
        context_text=context_text,
        selected_l1_examples=selected_l1,
        thinking_queue=c.get("thinking_delta_queue"),
    )
    if plan is None:
        plan = _fallback_plan()

    plan = enrich_sql_steps_from_reference_sql(plan, l1_sql)
    plan = _ensure_plan_visualization(plan, question)

    sql_exec_count = len(get_sql_execution_steps(plan))
    multi_sql = plan_requires_multi_sql(plan)
    l1_ids = [ex.id for ex in selected_l1]

    if plan.get("complexity") == "low" and not multi_sql and sql_exec_count <= 1:
        await _span(
            config,
            "plan_question",
            t0,
            "success",
            {
                "skipped": True,
                "reason": "llm_low_single_sql",
                "l1_selected_ids": l1_ids,
                "l1_count": len(selected_l1),
                "multi_sql": False,
                "context_chars": len(context_text),
                "plan": plan,
            },
        )
        return {"plan_skipped": True, "plan": plan, "visualization_intent": plan.get("visualization")}

    await _span(
        config,
        "plan_question",
        t0,
        "success",
        {
            "skipped": False,
            "complexity": plan.get("complexity"),
            "intent": plan.get("intent"),
            "multi_sql": multi_sql,
            "l1_selected_ids": l1_ids,
            "l1_count": len(selected_l1),
            "context_chars": len(context_text),
            "step_count": len(plan.get("steps") or []),
            "sql_exec_step_count": sql_exec_count,
            "plan": plan,
        },
    )
    plan = _inject_code_sources(plan, merged)
    return {
        "plan_skipped": False,
        "plan": plan,
        "visualization_intent": plan.get("visualization"),
        "tool_observations": [],
        "agent_steps": [],
        "agent_step_count": 0,
        "agent_loop_done": False,
        "use_agent_path": True,
        "intermediate_results": [],
        "sql_exec_step_index": 0,
        "sql_steps": [],
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

