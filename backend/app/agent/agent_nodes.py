"""
Agent 循环、上下文拼装与分步 SQL 节点（§11.7.4 · 第 8 周）。
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.agent_llm import (
    _fallback_action,
    _needs_tools_complete,
    decide_agent_action,
    is_duplicate_tool_call,
)
from app.agent.context_builder import build_agent_context_text
from app.agent.l1_nodes import _dicts_to_candidates
from app.agent.llm_sql import generate_sql_from_llm, generate_sql_step_from_llm
from app.agent.nodes import _cfg, _span, generate_sql
from app.agent.state import AskGraphState
from app.agent.tools.executor import execute_tool_span
from app.ask.l1_service import append_l1_to_context
from config.settings import Settings


async def agent_loop(state: AskGraphState, config: RunnableConfig) -> dict:
    """
    ReAct 工具循环：LLM 选 tool → 执行 → observation 追加。

    超 AGENT_MAX_STEPS 或 submit_final_sql 时设置 agent_loop_done。
    """
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or state.get("question") or ""
    plan = state.get("plan")
    merged = state.get("merged_recall")
    step_count = state.get("agent_step_count") or 0
    max_steps = settings.agent_max_steps

    if state.get("agent_loop_done"):
        return {}

    if not settings.agent_loop_enabled:
        await _span(config, "agent_loop", t0, "degraded", {"skipped": True, "reason": "disabled"})
        return {"agent_loop_done": True, "use_agent_path": True}

    if step_count >= max_steps:
        await _span(
            config,
            "agent_loop",
            t0,
            "degraded",
            {"done": True, "reason": "max_steps", "step_count": step_count},
        )
        return {"agent_loop_done": True, "use_agent_path": True, "agent_step_count": step_count}

    observations = list(state.get("tool_observations") or [])
    agent_steps = list(state.get("agent_steps") or [])
    default_tables = (merged.table_names if merged else [])[:5]

    # needs_tool 已完成后跳过 LLM，直接结束循环
    if _needs_tools_complete(plan, observations, default_tables=default_tables):
        await _span(
            config,
            "agent_loop",
            t0,
            "success",
            {
                "done": True,
                "reason": "needs_tool_complete",
                "step_count": step_count,
                "observation_count": len(observations),
            },
        )
        return {"agent_loop_done": True, "use_agent_path": True, "agent_step_count": step_count}

    action = await decide_agent_action(
        settings=settings,
        question=question,
        plan=plan,
        observations=observations,
        default_tables=default_tables,
        thinking_queue=c.get("thinking_delta_queue"),
    )

    if action.get("action") == "finish" and not observations and plan:
        forced = _fallback_action(plan, observations, default_tables=default_tables, question=question)
        if forced.get("action") == "tool":
            action = forced

    if action.get("action") == "finish":
        await _span(
            config,
            "agent_loop",
            t0,
            "success",
            {"done": True, "reason": "finish", "step_count": step_count},
        )
        return {"agent_loop_done": True, "use_agent_path": True, "agent_step_count": step_count}

    if action.get("action") == "ask_user" or action.get("tool") == "ask_user_question":
        if not settings.dialogue_agent_ask_enabled:
            await _span(
                config,
                "agent_loop",
                t0,
                "degraded",
                {"done": True, "reason": "ask_user_disabled", "step_count": step_count},
            )
            return {"agent_loop_done": True, "use_agent_path": True, "agent_step_count": step_count}
        args = action.get("args") or {}
        from app.agent.ask_user_payload import clip_ask_user_question

        ask_user = clip_ask_user_question(
            {
                "title": args.get("title") or "还需要确认一下",
                "reason": args.get("reason"),
                "questions": args.get("questions") or [],
            },
            max_questions=settings.dialogue_ask_max_questions,
            max_options=settings.dialogue_ask_max_options,
        )
        obs = {
            "tool": "ask_user_question",
            "args": args,
            "result": {"asked": True, "questions": (ask_user or {}).get("questions") or []},
        }
        observations.append(obs)
        agent_steps.append({"phase": "agent_loop", "tool": "ask_user_question", "step": step_count + 1})
        await _span(
            config,
            "agent_loop",
            t0,
            "success",
            {"done": True, "reason": "ask_user", "step_count": step_count + 1},
        )
        return {
            "tool_observations": observations,
            "agent_steps": agent_steps,
            "agent_step_count": step_count + 1,
            "agent_loop_done": True,
            "use_agent_path": True,
            "need_clarification": True,
            "dialogue_act": "clarify",
            "ready_to_execute": False,
            "ask_user_question": ask_user,
            "clarify_question": (ask_user or {}).get("reason")
            or "查询条件存在歧义，请确认后再继续。",
            "missing_slots": list(args.get("missing_slots") or ["metric"]),
        }

    tool_name = action.get("tool") or ""
    args = action.get("args") or {}

    # 执行前硬拦截：同 fingerprint 禁止再跑（防 LLM/路径漏网）
    if tool_name and is_duplicate_tool_call(tool_name, args, observations):
        forced = _fallback_action(plan, observations, default_tables=default_tables, question=question)
        if (
            forced.get("action") == "tool"
            and forced.get("tool")
            and not is_duplicate_tool_call(
                str(forced.get("tool") or ""),
                forced.get("args") if isinstance(forced.get("args"), dict) else {},
                observations,
            )
        ):
            action = forced
            tool_name = action.get("tool") or ""
            args = action.get("args") or {}
        else:
            obs = {
                "tool": tool_name,
                "args": args,
                "result": {"skipped": "duplicate", "fingerprint": True},
            }
            observations.append(obs)
            agent_steps.append({"phase": "agent_loop", "tool": tool_name, "step": step_count + 1})
            await _span(
                config,
                "agent_loop",
                t0,
                "success",
                {
                    "done": True,
                    "reason": "duplicate_tool_call",
                    "tool": tool_name,
                    "step_count": step_count + 1,
                },
            )
            return {
                "tool_observations": observations,
                "agent_steps": agent_steps,
                "agent_step_count": step_count + 1,
                "agent_loop_done": True,
                "use_agent_path": True,
            }

    result = await execute_tool_span(
        config,
        tool_name=tool_name,
        args=args,
        session=c["copilot_session"],
        settings=settings,
        ctx=c["ctx"],
        question=question,
        keywords=state.get("keywords"),
    )
    obs = {"tool": tool_name, "args": args, "result": result}
    observations.append(obs)
    agent_steps.append({"phase": "agent_loop", "tool": tool_name, "step": step_count + 1})
    step_count += 1

    needs_done = _needs_tools_complete(plan, observations, default_tables=default_tables)
    done = step_count >= max_steps or needs_done
    tool_detail: dict[str, Any] = {
        "done": done,
        "tool": tool_name,
        "step_count": step_count,
        "observation_count": len(observations),
    }
    if needs_done:
        tool_detail["reason"] = "needs_tool_complete"
    # 供前端推理段标题展示用途（表名/检索词等短参数）
    slim_args = {
        k: args[k]
        for k in ("table", "query", "keyword", "from_table", "to_table")
        if k in args and args[k] is not None
    }
    if slim_args:
        tool_detail["args"] = slim_args
        if "table" in slim_args:
            tool_detail["table"] = slim_args["table"]
    await _span(
        config,
        "agent_loop",
        t0,
        "success",
        tool_detail,
    )
    update: dict[str, Any] = {
        "tool_observations": observations,
        "agent_steps": agent_steps,
        "agent_step_count": step_count,
        "use_agent_path": True,
    }
    if done:
        update["agent_loop_done"] = True
    return update


def route_after_agent_loop(state: AskGraphState) -> str:
    """agent_loop 未结束时继续循环；ask_user 则澄清；否则进入 build_agent_context。"""
    if state.get("need_clarification"):
        return "ask_clarification"
    if state.get("agent_loop_done"):
        return "build_agent_context"
    return "agent_loop"


async def build_agent_context(state: AskGraphState, config: RunnableConfig) -> dict:
    """种子召回 + plan + observations 拼装 Agent 专用 Prompt。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or state.get("question") or ""
    merged = state.get("merged_recall")
    plan = state.get("plan")
    observations = state.get("tool_observations") or []

    context_text = await build_agent_context_text(
        question,
        merged,
        c["copilot_session"],
        c["ctx"],
        plan=plan,
        observations=observations,
        settings=settings,
        memory_prompt_text=state.get("memory_prompt_text") or "",
    )
    selected_l1 = _dicts_to_candidates(state.get("selected_l1_examples"))
    context_text = append_l1_to_context(context_text, selected_l1)

    await _span(
        config,
        "build_agent_context",
        t0,
        "success",
        {
            "chars": len(context_text),
            "context_text": context_text,
            "observation_count": len(observations),
            "plan_steps": len((plan or {}).get("steps") or []),
        },
    )
    return {"context_text": context_text}


async def generate_sql_step(state: AskGraphState, config: RunnableConfig) -> dict:
    """按 plan.steps 生成分步 CTE SQL；plan_skipped 时委托 generate_sql。"""
    if state.get("plan_skipped"):
        return await generate_sql(state, config)

    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    context_text = state.get("context_text") or ""
    plan = state.get("plan") or {}
    plan_steps = plan.get("steps") or []

    if not plan_steps:
        return await generate_sql(state, config)

    thinking_queue = c.get("thinking_delta_queue")
    sql, sql_steps_meta, token_in, token_out = await generate_sql_step_from_llm(
        settings=settings,
        question=question,
        context_text=context_text,
        plan_steps=plan_steps,
        plan=plan,
        thinking_queue=thinking_queue,
    )
    gen_ms = int((time.perf_counter() - t0) * 1000)
    retry_count = state.get("retry_count") or 0
    l2_retry = False

    if not sql and retry_count < 1:
        l2_retry = True
        sql, token_in2, token_out2 = await generate_sql_from_llm(
            settings=settings,
            question=question,
            context_text=context_text,
            compact=True,
            thinking_queue=thinking_queue,
        )
        retry_count += 1
        token_in = (token_in or 0) + (token_in2 or 0) if token_in2 else token_in
        token_out = (token_out or 0) + (token_out2 or 0) if token_out2 else token_out

    await _span(
        config,
        "generate_sql_step",
        t0,
        "success" if sql else "fail",
        {
            "retry_count": retry_count,
            "has_sql": bool(sql),
            "l2_retry": l2_retry,
            "sql_step_count": len(sql_steps_meta),
            "token_in": token_in,
            "token_out": token_out,
            "sql_preview": sql,
            "error_code": None if sql else "LLM_NO_SQL",
            "error_message": None
            if sql
            else "未能生成分步 SQL，请换种问法或标记 badcase",
        },
    )

    if not sql:
        return {
            "status": "fail",
            "error_code": "LLM_NO_SQL",
            "error_message": "未能生成分步 SQL，请换种问法或标记 badcase",
            "latency_ms_sql_gen": gen_ms,
            "retry_count": retry_count,
            "degrade_level": 3,
            "token_in": token_in,
            "token_out": token_out,
        }

    return {
        "raw_sql": sql,
        "sql_steps": sql_steps_meta,
        "degrade_level": 0,
        "latency_ms_sql_gen": gen_ms,
        "retry_count": retry_count,
        "token_in": token_in,
        "token_out": token_out,
        "value_column": "cnt",
        "answer_template": "根据查询结果，共返回 {row_count} 行数据。",
    }
