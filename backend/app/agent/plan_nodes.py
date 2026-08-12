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
from app.agent.plan_analyzer import apply_plan_structure_analysis, detect_multi_branch_aggregate
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
from app.meta.repository import MetaRepository
from config.settings import Settings


async def _analyze_plan_structure(
    plan: dict[str, Any],
    merged: MergedRecallContext | None,
    copilot_session,
) -> dict[str, Any]:
    """Python 结构分析：多来源表无直连时强制 subquery_per_branch。"""
    if merged is None or not merged.table_names:
        return plan

    repo = MetaRepository(copilot_session)
    relations = await repo.list_relations()
    table_meta: dict[str, Any] = {}
    column_map: dict[str, Any] = {}
    for name in merged.table_names[:12]:
        row = await repo.find_table_by_name(name)
        if row is None:
            continue
        table_meta[row.table_name] = row
        column_map[row.table_name] = await repo.get_column_map(row.id)

    analysis = detect_multi_branch_aggregate(
        recalled_tables=merged.table_names,
        relations=relations,
        table_meta=table_meta,
        column_map=column_map,
        metrics=plan.get("metrics"),
    )
    return apply_plan_structure_analysis(plan, analysis)


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
        "ready_to_execute": True,
        "missing_slots": [],
        "ambiguities": [],
        "ask_user_question": None,
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


def _plan_requires_agent_path(plan: dict[str, Any]) -> bool:
    """结构复杂或需分路聚合时不得走 plan_skipped 快路径。"""
    if plan.get("aggregate_strategy") == "subquery_per_branch":
        return True
    if plan.get("query_shape") == "multi_branch_aggregate":
        return True
    return False


def _should_skip_plan(plan: dict[str, Any]) -> bool:
    if _plan_requires_agent_path(plan):
        return False
    sql_exec_count = len(get_sql_execution_steps(plan))
    multi_sql = plan_requires_multi_sql(plan)
    return (
        plan.get("complexity") == "low"
        and not multi_sql
        and sql_exec_count <= 1
    )


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
    plan = await _analyze_plan_structure(plan, merged, c["copilot_session"])
    plan = _ensure_plan_visualization(plan, question)

    sql_exec_count = len(get_sql_execution_steps(plan))
    multi_sql = plan_requires_multi_sql(plan)
    l1_ids = [ex.id for ex in selected_l1]
    skip_plan = _should_skip_plan(plan)

    span_plan = {
        "complexity": plan.get("complexity"),
        "intent": plan.get("intent"),
        "multi_sql": multi_sql,
        "query_shape": plan.get("query_shape"),
        "aggregate_strategy": plan.get("aggregate_strategy"),
        "anchor_table": plan.get("anchor_table"),
        "structure_reason": plan.get("structure_reason"),
        "l1_selected_ids": l1_ids,
        "l1_count": len(selected_l1),
        "context_chars": len(context_text),
        "step_count": len(plan.get("steps") or []),
        "sql_exec_step_count": sql_exec_count,
        "plan": plan,
    }

    if skip_plan and plan.get("ready_to_execute") is not False:
        await _span(
            config,
            "plan_question",
            t0,
            "success",
            {
                "skipped": True,
                "reason": "llm_low_single_sql",
                "multi_sql": False,
                **span_plan,
            },
        )
        return {
            "plan_skipped": True,
            "plan": plan,
            "visualization_intent": plan.get("visualization"),
            "ready_to_execute": True,
        }

    if plan.get("ready_to_execute") is False:
        missing = list(plan.get("missing_slots") or [])
        ask_user = plan.get("ask_user_question")
        ask_user_dict = ask_user if isinstance(ask_user, dict) else None
        # 仅有 soft ambiguity、无缺槽且无出题载荷：按规划默认口径继续，不打断追问
        if not missing and not ask_user_dict:
            await _span(
                config,
                "plan_question",
                t0,
                "success",
                {
                    "skipped": False,
                    "ready_to_execute": True,
                    "soft_ambiguities": plan.get("ambiguities") or [],
                    **span_plan,
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
                "ready_to_execute": True,
                "need_clarification": False,
            }
        await _span(
            config,
            "plan_question",
            t0,
            "success",
            {
                "skipped": False,
                "ready_to_execute": False,
                "missing_slots": missing,
                **span_plan,
            },
        )
        return {
            "plan_skipped": False,
            "plan": plan,
            "visualization_intent": plan.get("visualization"),
            "ready_to_execute": False,
            "need_clarification": True,
            "dialogue_act": "clarify",
            "missing_slots": missing,
            "ask_user_question": ask_user_dict,
            "clarify_question": (
                "；".join(plan.get("ambiguities") or [])
                or "查询条件存在歧义，请补充后再试。"
            ),
        }

    await _span(
        config,
        "plan_question",
        t0,
        "success",
        {
            "skipped": False,
            **span_plan,
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
        "ready_to_execute": True,
    }


def route_after_plan(state: AskGraphState) -> str:
    """plan_question 之后：澄清 / 快路径 generate_sql / 复杂问句进 agent_loop。"""
    if state.get("error_code"):
        return "format_answer"
    if state.get("need_clarification") or state.get("ready_to_execute") is False:
        # plan 明确 not ready，或召回闸已标记
        if state.get("dialogue_act") == "clarify" or state.get("need_clarification"):
            return "ask_clarification"
        plan = state.get("plan") or {}
        if plan.get("ready_to_execute") is False:
            return "ask_clarification"
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

