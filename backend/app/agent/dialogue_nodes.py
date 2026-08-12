"""
对话门禁 LangGraph 节点：route_dialogue / reply_chat / ask_clarification。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.ask_user_payload import (
    answers_to_text,
    build_ask_user_from_slots,
    clarification_payload_dict,
    clip_ask_user_question,
    flatten_ask_user,
    new_clarification_thread_id,
)
from app.agent.dialogue_llm import route_dialogue_llm
from app.agent.dialogue_rules import detect_topic_switch, rule_route_dialogue
from app.agent.nodes import _span
from app.agent.state import AskGraphState
from app.core.log_config import get_logger
from app.memory.memory_service import MemoryService
from config.settings import Settings

logger = get_logger("dialogue")


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


def _merge_pending_answer(
    question: str,
    pending: dict[str, Any],
    answers: list[dict[str, Any]] | None,
) -> tuple[str, dict[str, Any], list[str]]:
    """合并 pending + 本轮作答，返回 (resolved, filled, still_missing)。"""
    filled = dict(pending.get("filled_slots") or {})
    missing = list(pending.get("missing_slots") or [])
    original = str(pending.get("original_question") or "")
    ask_user = pending.get("ask_user_question")

    patch = answers_to_text(answers, ask_user)
    user_text = (question or "").strip()
    supplement = patch or user_text

    still: list[str] = []
    time_labels = (
        "近7天",
        "近七天",
        "本月",
        "本周",
        "本年",
        "今年",
        "今日",
        "昨天",
        "昨日",
        "上周",
    )
    metric_hints = (
        "人数",
        "人次",
        "数量",
        "次数",
        "金额",
        "销量",
        "销售",
        "销售额",
        "订单",
        "趋势",
        "占比",
        "排名",
        "总量",
        "汇总",
        "营收",
        "收入",
    )
    for slot in missing:
        if slot == "time_range" and any(k in supplement for k in time_labels):
            for label in time_labels:
                if label in supplement:
                    filled["time_range"] = "近7天" if label == "近七天" else label
                    break
        elif slot == "metric" and any(k in supplement for k in metric_hints):
            # 优先截取用户原话中的指标片段，避免写死行业指标名
            filled[slot] = supplement
        elif slot == "entity" and supplement and len(supplement) <= 20:
            filled[slot] = supplement
        elif slot in ("scope", "dimension") and supplement:
            filled[slot] = supplement
        else:
            still.append(slot)

    if any(k in supplement for k in metric_hints) and "metric" in still:
        still.remove("metric")
        filled.setdefault("metric", supplement)
    if any(k in supplement for k in ("近7天", "本月", "本周", "本年", "今年")) and "time_range" in still:
        still.remove("time_range")
        for label in ("近7天", "本月", "本周", "本年", "今年"):
            if label in supplement:
                filled["time_range"] = label
                break

    if original and supplement and supplement != original:
        resolved = f"{original} {supplement}".strip()
    else:
        resolved = original or supplement or question
    return resolved, filled, still


async def route_dialogue(state: AskGraphState, config: RunnableConfig) -> dict:
    """对话分流：读 pending → 规则/LLM → 写 dialogue_act / resolved_question。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or state.get("question") or ""

    if not settings.dialogue_gate_enabled:
        await _span(config, "route_dialogue", t0, "degraded", {"skipped": True, "reason": "disabled"})
        return {
            "dialogue_act": "data_query",
            "dialogue_gate_skipped": True,
            "ready_to_execute": True,
            "resolved_question": question,
        }

    memory = state.get("session_memory")
    pending = state.get("pending_clarification")
    if pending is None and memory is not None:
        pending = getattr(memory, "pending_clarification", None)
    answers = state.get("clarification_answers")
    thread_id = state.get("clarification_thread_id")

    if pending and thread_id and pending.get("thread_id") and thread_id != pending.get("thread_id"):
        answers = None

    if pending:
        cancel_hit = (rule_route_dialogue(question) or {}).get("cancel_pending")
        if detect_topic_switch(question, pending) or cancel_hit:
            svc = MemoryService(c["copilot_session"], settings)
            await svc.clear_pending_clarification(c.get("session_id"), c["ctx"].user_id)
            pending = None
        else:
            resolved, filled, still = _merge_pending_answer(question, pending, answers)
            ask_count = int(pending.get("ask_count") or 1)
            if still and ask_count >= settings.dialogue_clarify_max_asks:
                await _span(
                    config,
                    "route_dialogue",
                    t0,
                    "success",
                    {"dialogue_act": "clarify", "reason": "max_asks", "ask_count": ask_count},
                )
                ask_user = build_ask_user_from_slots(
                    missing_slots=still,
                    filled_slots=filled,
                    reason="已多次补充仍不完整，请换一种完整问法",
                    max_questions=settings.dialogue_ask_max_questions,
                    max_options=settings.dialogue_ask_max_options,
                )
                _flat_q, flat_opts = flatten_ask_user(ask_user)
                return {
                    "dialogue_act": "clarify",
                    "dialogue_confidence": 1.0,
                    "resolved_question": resolved,
                    "missing_slots": still,
                    "filled_slots": filled,
                    "clarify_question": (
                        "已达到澄清上限。请用一句完整问题重试，例如「本月销售额是多少」。"
                    ),
                    "clarify_options": flat_opts,
                    "ask_user_question": ask_user,
                    "pending_clarification": {
                        **pending,
                        "filled_slots": filled,
                        "missing_slots": still,
                        "ask_count": ask_count,
                    },
                    "need_clarification": True,
                    "ready_to_execute": False,
                    "status": "need_clarification",
                }
            if still:
                await _span(
                    config,
                    "route_dialogue",
                    t0,
                    "success",
                    {"dialogue_act": "clarify", "reason": "still_missing", "missing": still},
                )
                ask_user = build_ask_user_from_slots(
                    missing_slots=still,
                    filled_slots=filled,
                    max_questions=settings.dialogue_ask_max_questions,
                    max_options=settings.dialogue_ask_max_options,
                )
                flat_q, flat_opts = flatten_ask_user(ask_user)
                return {
                    "dialogue_act": "clarify",
                    "dialogue_confidence": 0.9,
                    "resolved_question": resolved,
                    "missing_slots": still,
                    "filled_slots": filled,
                    "clarify_question": flat_q,
                    "clarify_options": flat_opts,
                    "ask_user_question": ask_user,
                    "pending_clarification": {
                        **pending,
                        "filled_slots": filled,
                        "missing_slots": still,
                        "resolved_partial": resolved,
                    },
                    "need_clarification": True,
                    "ready_to_execute": False,
                    "normalized_question": resolved,
                    "recall_question": resolved,
                }
            svc = MemoryService(c["copilot_session"], settings)
            await svc.clear_pending_clarification(c.get("session_id"), c["ctx"].user_id)
            await _span(
                config,
                "route_dialogue",
                t0,
                "success",
                {"dialogue_act": "data_query", "reason": "pending_merged", "resolved": resolved},
            )
            return {
                "dialogue_act": "data_query",
                "dialogue_confidence": 0.92,
                "resolved_question": resolved,
                "missing_slots": [],
                "filled_slots": filled,
                "pending_clarification": None,
                "need_clarification": False,
                "ready_to_execute": True,
                "normalized_question": resolved,
                "recall_question": resolved,
            }

    route = rule_route_dialogue(
        question,
        pending=None,
        require_time_slot=settings.dialogue_require_time_slot,
    )
    if route and route.get("cancel_pending"):
        svc = MemoryService(c["copilot_session"], settings)
        await svc.clear_pending_clarification(c.get("session_id"), c["ctx"].user_id)

    if route is None and settings.dialogue_gate_llm_enabled:
        route = await route_dialogue_llm(
            settings=settings,
            question=question,
            pending=None,
            thinking_queue=c.get("thinking_delta_queue"),
        )

    if route is None:
        if settings.dialogue_fail_open:
            await _span(
                config,
                "route_dialogue",
                t0,
                "degraded",
                {"dialogue_act": "data_query", "reason": "fail_open"},
            )
            return {
                "dialogue_act": "data_query",
                "dialogue_confidence": 0.4,
                "resolved_question": question,
                "ready_to_execute": True,
                "degrade_level": max(state.get("degrade_level") or 0, 1),
            }
        await _span(
            config,
            "route_dialogue",
            t0,
            "success",
            {"dialogue_act": "out_of_scope", "reason": "fail_closed"},
        )
        return {
            "dialogue_act": "out_of_scope",
            "dialogue_confidence": 0.5,
            "resolved_question": question,
            "answer": "暂时无法判断问题类型，请换一种更完整的问数说法后再试。",
            "ready_to_execute": False,
        }

    act = route["dialogue_act"]
    confidence = float(route.get("confidence") or 0.6)
    if confidence < settings.dialogue_min_confidence and act == "data_query":
        act = "clarify"
        route = {
            **route,
            "dialogue_act": "clarify",
            "missing_slots": route.get("missing_slots") or ["metric", "time_range"],
            "clarify_question": route.get("clarify_question")
            or "问题不够明确，请补充时间范围与指标。",
            "reason": (route.get("reason") or "") + ";low_confidence",
        }

    resolved = route.get("resolved_question") or question
    detail = {
        "dialogue_act": act,
        "confidence": confidence,
        "missing_slots": route.get("missing_slots"),
        "reason": route.get("reason"),
        "source": route.get("source"),
        "resolved_question": resolved,
    }
    await _span(config, "route_dialogue", t0, "success", detail)

    out: dict[str, Any] = {
        "dialogue_act": act,
        "dialogue_confidence": confidence,
        "resolved_question": resolved,
        "missing_slots": list(route.get("missing_slots") or []),
        "filled_slots": dict(route.get("filled_slots") or {}),
        "clarify_question": route.get("clarify_question"),
        "clarify_options": list(route.get("clarify_options") or []),
        "ready_to_execute": act == "data_query",
        "need_clarification": act == "clarify",
        "pending_clarification": None if act == "data_query" else state.get("pending_clarification"),
    }
    if route.get("chat_reply"):
        out["answer"] = route["chat_reply"]
    if act == "data_query" and resolved != question:
        out["normalized_question"] = resolved
        out["recall_question"] = resolved
    return out


def route_after_dialogue(state: AskGraphState) -> str:
    """route_dialogue 之后分流。"""
    if not state.get("dialogue_gate_skipped") and state.get("dialogue_act") in (
        "chitchat",
        "out_of_scope",
    ):
        return "reply_chat"
    if state.get("dialogue_act") == "clarify" or state.get("need_clarification"):
        return "ask_clarification"
    return "process_memory_context"


async def reply_chat(state: AskGraphState, config: RunnableConfig) -> dict:
    """闲聊 / 域外答复；零召回。"""
    t0 = time.perf_counter()
    act = state.get("dialogue_act") or "chitchat"
    answer = state.get("answer")
    if not answer:
        if act == "out_of_scope":
            answer = "这个问题不在问数范围内。请提出与业务数据相关的问题。"
        else:
            answer = (
                "你好！我是智能问数助手，可基于业务元数据查询数据。"
                "试试：「本月销售额是多少」或「最近7天订单趋势」。"
            )
    status = "out_of_scope" if act == "out_of_scope" else "chitchat"
    c = _cfg(config)
    trace_id = c.get("trace_id", "-")
    session_id = c.get("session_id")
    user_id = c["ctx"].user_id
    logger.info(
        "[trace=%s] reply_chat 开始 act=%s status=%s session_id=%s has_answer=%s",
        trace_id,
        act,
        status,
        session_id,
        bool(answer),
    )
    t_span = time.perf_counter()
    await _span(config, "reply_chat", t0, "success", {"dialogue_act": act, "status": status})
    logger.info(
        "[trace=%s] reply_chat span 已写入 duration_ms=%s，开始 clear_pending",
        trace_id,
        int((time.perf_counter() - t_span) * 1000),
    )
    settings: Settings = c["settings"]
    svc = MemoryService(c["copilot_session"], settings)
    t_clear = time.perf_counter()
    try:
        await svc.clear_pending_clarification(session_id, user_id)
        logger.info(
            "[trace=%s] reply_chat clear_pending 完成 duration_ms=%s",
            trace_id,
            int((time.perf_counter() - t_clear) * 1000),
        )
    except Exception:
        logger.exception(
            "[trace=%s] reply_chat clear_pending 失败 duration_ms=%s session_id=%s",
            trace_id,
            int((time.perf_counter() - t_clear) * 1000),
            session_id,
        )
        raise
    logger.info(
        "[trace=%s] reply_chat 即将返回 total_ms=%s",
        trace_id,
        int((time.perf_counter() - t0) * 1000),
    )
    return {
        "answer": answer,
        "status": status,
        "columns": None,
        "rows": None,
        "final_sql": None,
        "need_clarification": False,
        "ready_to_execute": False,
        "pending_clarification": None,
    }


async def ask_clarification(state: AskGraphState, config: RunnableConfig) -> dict:
    """落盘 AskUserQuestion / pending，返回 need_clarification。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]

    missing = list(state.get("missing_slots") or [])
    filled = dict(state.get("filled_slots") or {})
    ask_user = state.get("ask_user_question")
    if ask_user:
        ask_user = clip_ask_user_question(
            ask_user,
            max_questions=settings.dialogue_ask_max_questions,
            max_options=settings.dialogue_ask_max_options,
        )
    if not ask_user:
        plan = state.get("plan") or {}
        if isinstance(plan.get("ask_user_question"), dict):
            ask_user = clip_ask_user_question(
                plan["ask_user_question"],
                max_questions=settings.dialogue_ask_max_questions,
                max_options=settings.dialogue_ask_max_options,
            )
        if not ask_user and missing:
            # 仅在有明确缺槽时按槽出题；禁止空槽时默认塞 time_range/metric
            ask_user = build_ask_user_from_slots(
                missing_slots=missing,
                filled_slots=filled,
                clarify_question=state.get("clarify_question"),
                clarify_options=state.get("clarify_options"),
                max_questions=settings.dialogue_ask_max_questions,
                max_options=settings.dialogue_ask_max_options,
            )
        if not ask_user:
            # plan/agent 仅给出歧义说明：自由文本确认，不发明时间/指标题
            clarify_text = (
                state.get("clarify_question")
                or "查询条件存在歧义，请补充说明或直接发送完整问句。"
            )
            opts_raw = list(state.get("clarify_options") or [])
            options = [
                {"id": f"o{i}", "label": str(o).strip(), "recommended": i == 0}
                for i, o in enumerate(opts_raw)
                if str(o).strip()
            ][: settings.dialogue_ask_max_options]
            ask_user = clip_ask_user_question(
                {
                    "title": "还需要确认一下",
                    "reason": clarify_text,
                    "questions": [
                        {
                            "id": "general",
                            "prompt": "请确认或补充说明（也可直接发送完整问句）",
                            "allow_free_text": True,
                            "options": options,
                        }
                    ],
                },
                max_questions=settings.dialogue_ask_max_questions,
                max_options=settings.dialogue_ask_max_options,
            )

    flat_q, flat_opts = flatten_ask_user(ask_user)
    clarify_q = state.get("clarify_question") or flat_q or "请补充查询条件后再试。"
    clarify_opts = state.get("clarify_options") or flat_opts

    prev = state.get("pending_clarification") or {}
    thread_id = prev.get("thread_id") or new_clarification_thread_id()
    ask_count = int(prev.get("ask_count") or 0) + 1
    source = "dialogue_gate"
    if state.get("plan") and state.get("merged_recall") is not None:
        source = "plan"
    observations = state.get("tool_observations") or []
    if any(o.get("tool") == "ask_user_question" for o in observations):
        source = "agent"

    pending = {
        "thread_id": thread_id,
        "original_question": prev.get("original_question")
        or state.get("question")
        or state.get("normalized_question")
        or "",
        "resolved_partial": state.get("resolved_question"),
        "filled_slots": filled or prev.get("filled_slots") or {},
        "missing_slots": missing,
        "ask_user_question": ask_user,
        "clarify_question": clarify_q,
        "candidates": prev.get("candidates") or {},
        "ask_count": ask_count,
        "source": source,
        "trace_id": state.get("trace_id"),
        "created_at": prev.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }

    svc = MemoryService(c["copilot_session"], settings)
    await svc.save_pending_clarification(
        c.get("session_id"),
        c["ctx"].user_id,
        pending,
    )

    clarification = clarification_payload_dict(
        ask_user=ask_user,
        missing_slots=missing,
        partial_question=state.get("resolved_question") or state.get("normalized_question"),
        thread_id=thread_id,
        clarify_question=clarify_q,
        clarify_options=clarify_opts,
    )
    answer = clarify_q
    if ask_user and ask_user.get("reason"):
        answer = f"{ask_user['reason']}\n{clarify_q}"

    await _span(
        config,
        "ask_clarification",
        t0,
        "success",
        {
            "thread_id": thread_id,
            "ask_count": ask_count,
            "missing_slots": missing,
            "source": source,
            "questions": len((ask_user or {}).get("questions") or []),
        },
    )
    return {
        "status": "need_clarification",
        "answer": answer,
        "ask_user_question": ask_user,
        "clarify_question": clarify_q,
        "clarify_options": clarify_opts,
        "pending_clarification": pending,
        "need_clarification": True,
        "ready_to_execute": False,
        "columns": None,
        "rows": None,
        "final_sql": None,
        "error_code": None,
        "error_message": None,
        "dialogue_act": state.get("dialogue_act") or "clarify",
        "_clarification_payload": clarification,
    }


def route_after_merge_recall(state: AskGraphState) -> str:
    """召回二次闸门后分流：澄清 / 域外拒答 / 继续 L1。"""
    if state.get("need_clarification"):
        return "ask_clarification"
    if state.get("status") in ("out_of_scope", "chitchat"):
        return "format_answer"
    if state.get("error_code"):
        return "format_answer"
    return "do_recall_sql_examples"
