"""
召回二次闸门：规则预筛 + LLM 裁决（proceed / clarify / out_of_scope）。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.ask_user_payload import build_ask_user_from_slots, clip_ask_user_question
from app.agent.context_builder import MergedRecallContext
from app.agent.llm_client import complete_messages
from app.agent.plan_llm import _extract_json
from config.settings import Settings

_VALID_DECISIONS = frozenset({"proceed", "clarify", "out_of_scope"})
_VALID_SLOTS = frozenset({"time_range", "metric", "entity", "scope", "dimension"})

_METRIC_HINTS = (
    "人数",
    "人次",
    "数量",
    "次数",
    "金额",
    "销量",
    "销售",
    "销售额",
    "订单",
    "占比",
    "趋势",
    "汇总",
    "营收",
    "收入",
)


def recall_gate_rule_flags(
    merged: MergedRecallContext,
    settings: Settings,
    question: str,
) -> dict[str, Any]:
    """规则预筛：是否触发 LLM 裁决及原因标记。"""
    top_table = merged.recalled_tables[0].score if merged.recalled_tables else 0.0
    top_metric = merged.metrics[0].score if merged.metrics else 0.0
    empty_recall = not merged.recalled_tables and not merged.metrics
    low_table = bool(merged.recalled_tables) and top_table < settings.dialogue_recall_table_min
    q = question or ""
    looks_metric = any(k in q for k in _METRIC_HINTS)
    low_metric = looks_metric and (
        not merged.metrics or top_metric < settings.dialogue_recall_metric_min
    )
    should = empty_recall or low_table or low_metric
    return {
        "should_adjudicate": should,
        "empty_recall": empty_recall,
        "low_table": low_table,
        "low_metric": low_metric,
        "looks_metric": looks_metric,
        "top_table_score": top_table,
        "top_metric_score": top_metric,
    }


def build_recall_gate_context(merged: MergedRecallContext) -> str:
    """拼装给裁决 LLM 的召回摘要（含表字段清单，便于判定 order_total 等度量）。"""
    tables: list[dict[str, Any]] = []
    for t in (merged.recalled_tables or [])[:8]:
        name = t.table_name
        tables.append(
            {
                "table": name,
                "score": round(float(t.score), 4),
                "search_text": (t.search_text or "")[:120],
                "prompt_columns": (merged.prompt_columns or {}).get(name, [])[:16],
            }
        )
    columns = [
        {
            "table": c.table_name,
            "column": c.column_name,
            "score": round(float(c.score), 4),
            "search_text": (c.search_text or "")[:100],
        }
        for c in (merged.columns or [])[:8]
    ]
    metrics = [
        {
            "code": m.metric_code,
            "name": m.metric_name,
            "score": round(float(m.score), 4),
            "tables": m.relevant_tables,
            "search_text": (m.search_text or "")[:100],
        }
        for m in (merged.metrics or [])[:6]
    ]
    return json.dumps(
        {"tables": tables, "columns": columns, "metrics": metrics},
        ensure_ascii=False,
    )


def _normalize_adjudication(
    raw: dict[str, Any],
    *,
    question: str,
    flags: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    decision = str(raw.get("decision") or "").strip().lower()
    if decision not in _VALID_DECISIONS:
        # 兼容误用 dialogue_act
        act = str(raw.get("dialogue_act") or "").strip().lower()
        if act == "data_query":
            decision = "proceed"
        elif act == "clarify":
            decision = "clarify"
        elif act == "out_of_scope":
            decision = "out_of_scope"
        else:
            decision = "clarify"

    reason = str(raw.get("reason") or "").strip() or None
    answer = str(raw.get("answer") or raw.get("chat_reply") or "").strip() or None

    missing = raw.get("missing_slots") or []
    if not isinstance(missing, list):
        missing = []
    missing_slots = [str(s) for s in missing if str(s) in _VALID_SLOTS]

    ask_user = raw.get("ask_user_question")
    if isinstance(ask_user, dict):
        ask_user = clip_ask_user_question(
            ask_user,
            max_questions=settings.dialogue_ask_max_questions,
            max_options=settings.dialogue_ask_max_options,
        )
    else:
        ask_user = None

    if decision == "clarify" and not ask_user:
        clarify_q = str(raw.get("clarify_question") or "").strip() or None
        opts = raw.get("clarify_options") or []
        if not isinstance(opts, list):
            opts = []
        clarify_options = [str(o).strip() for o in opts if str(o).strip()][:4]
        metric_opts = clarify_options or None
        slots = missing_slots or (["metric"] if flags.get("low_metric") else ["entity", "metric"])
        ask_user = build_ask_user_from_slots(
            missing_slots=slots,
            clarify_question=clarify_q or reason or "请补充后再查询",
            metric_candidates=metric_opts,
            reason=reason or clarify_q or "召回结果与问句相关度不足，需要确认",
            max_questions=settings.dialogue_ask_max_questions,
            max_options=settings.dialogue_ask_max_options,
        )
        missing_slots = slots

    if decision == "out_of_scope" and not answer:
        answer = (
            reason
            or "当前元数据里没有与该问句足够相关的表或指标，请换一种问法或先在元数据中配置对应度量。"
        )

    return {
        "decision": decision,
        "reason": reason,
        "answer": answer,
        "missing_slots": missing_slots,
        "ask_user_question": ask_user,
        "source": "llm",
    }


def build_rule_fallback_clarify(
    merged: MergedRecallContext,
    flags: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    """LLM 不可用时的规则兜底澄清（不推荐无关指标为唯一选项）。"""
    metric_opts = [m.metric_name or m.metric_code for m in (merged.metrics or [])[:4] if m]
    # 低分噪声候选不塞进 options，避免「活动人数」误导销售额问句
    use_metric_opts = bool(flags.get("low_metric") and not flags.get("low_table") and metric_opts)
    reason = "未找到足够相关的数据表或指标，请补充或换一种问法"
    if use_metric_opts:
        reason = "找到多个相近指标，请确认你关注哪一个"
    slots = ["metric"] if flags.get("low_metric") and not flags.get("low_table") else ["entity", "metric"]
    ask_user = build_ask_user_from_slots(
        missing_slots=slots,
        clarify_question=reason,
        metric_candidates=[str(x) for x in metric_opts if x] if use_metric_opts else None,
        reason=reason,
        max_questions=settings.dialogue_ask_max_questions,
        max_options=settings.dialogue_ask_max_options,
    )
    return {
        "decision": "clarify",
        "reason": reason,
        "answer": None,
        "missing_slots": slots,
        "ask_user_question": ask_user,
        "source": "rule_fallback",
    }


async def adjudicate_recall_gate_llm(
    *,
    settings: Settings,
    question: str,
    merged: MergedRecallContext,
    flags: dict[str, Any],
    thinking_queue: Any | None = None,
) -> dict[str, Any] | None:
    """
    对规则预筛命中的低置信召回做 LLM 裁决。

    Returns:
        规范化裁决 dict；失败返回 None。
    """
    ctx_json = build_recall_gate_context(merged)
    flags_json = json.dumps(
        {
            "empty_recall": flags.get("empty_recall"),
            "low_table": flags.get("low_table"),
            "low_metric": flags.get("low_metric"),
            "top_table_score": flags.get("top_table_score"),
            "top_metric_score": flags.get("top_metric_score"),
            "table_min": settings.dialogue_recall_table_min,
            "metric_min": settings.dialogue_recall_metric_min,
        },
        ensure_ascii=False,
    )
    system = (
        "你是企业问数系统的召回裁决助手。只输出 JSON，不要 markdown。\n"
        "规则预筛已判定召回分数偏低或为空；请根据「用户问句」与「召回摘要」裁决下一步。\n"
        "decision 取值：\n"
        "- proceed：召回虽分低，但表/字段足以支撑问句（例如问销售额且有 order/order_total），"
        "应继续生成 SQL，不要追问无关指标。\n"
        "- clarify：确有歧义，需要向用户提问；必须给出与问句语义相关的 options，"
        "禁止推荐明显无关的指标（如问销售额却推荐活动参与人数）。\n"
        "- out_of_scope：库内元数据无法支撑该问句，直接说明原因，不要假装有候选。\n"
        "原则：错答成本高，但「假选项误导」成本也高；能 proceed 就不要 clarify；"
        "无相关候选就 out_of_scope。\n"
        "输出字段：decision,reason,answer,missing_slots,ask_user_question,"
        "clarify_question,clarify_options\n"
        "ask_user_question 结构："
        '{"title":"...","reason":"...","questions":[{"id":"...","prompt":"...",'
        '"allow_free_text":true,"options":[{"id":"...","label":"...","recommended":false}]}]}\n'
        "clarify 时优先填 ask_user_question；out_of_scope 时填 answer。\n"
    )
    user = (
        f"用户问句：{question}\n\n"
        f"规则预筛标记：{flags_json}\n\n"
        f"召回摘要：{ctx_json}\n\n"
        "请输出裁决 JSON。"
    )
    try:
        content, _r, _ti, _to = await complete_messages(
            settings,
            [SystemMessage(content=system), HumanMessage(content=user)],
            thinking_queue=thinking_queue,
        )
        parsed = _extract_json(content)
        if not parsed:
            return None
        return _normalize_adjudication(
            parsed, question=question, flags=flags, settings=settings
        )
    except Exception:
        return None
