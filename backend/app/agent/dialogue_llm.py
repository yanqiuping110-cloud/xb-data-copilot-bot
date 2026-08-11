"""
对话门禁 LLM：输出 dialogue_act 结构化 JSON。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_client import complete_messages
from app.agent.plan_llm import _extract_json
from config.settings import Settings

_VALID_ACTS = frozenset({"chitchat", "clarify", "data_query", "out_of_scope"})
_VALID_SLOTS = frozenset({"time_range", "metric", "entity", "scope", "dimension"})


def _normalize_route(raw: dict[str, Any], *, question: str) -> dict[str, Any]:
    act = str(raw.get("dialogue_act") or "data_query").strip().lower()
    if act not in _VALID_ACTS:
        act = "data_query"
    try:
        confidence = float(raw.get("confidence") if raw.get("confidence") is not None else 0.6)
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    missing = raw.get("missing_slots") or []
    if not isinstance(missing, list):
        missing = []
    missing_slots = [str(s) for s in missing if str(s) in _VALID_SLOTS]

    filled = raw.get("filled_slots") if isinstance(raw.get("filled_slots"), dict) else {}
    filled_slots = {str(k): str(v) for k, v in filled.items() if v is not None and str(v).strip()}

    options = raw.get("clarify_options") or []
    if not isinstance(options, list):
        options = []
    clarify_options = [str(o).strip() for o in options if str(o).strip()][:4]

    resolved = str(raw.get("resolved_question") or question).strip() or question
    return {
        "dialogue_act": act,
        "confidence": confidence,
        "resolved_question": resolved,
        "missing_slots": missing_slots,
        "filled_slots": filled_slots,
        "clarify_question": (str(raw.get("clarify_question")).strip() if raw.get("clarify_question") else None),
        "clarify_options": clarify_options,
        "assumptions": raw.get("assumptions") if isinstance(raw.get("assumptions"), list) else [],
        "reason": str(raw.get("reason") or "").strip() or None,
        "chat_reply": (str(raw.get("chat_reply")).strip() if raw.get("chat_reply") else None),
        "source": "llm",
    }


async def route_dialogue_llm(
    *,
    settings: Settings,
    question: str,
    pending: dict[str, Any] | None = None,
    thinking_queue: Any | None = None,
) -> dict[str, Any] | None:
    """调用轻量 LLM 做对话分流；失败返回 None。"""
    pending_text = json.dumps(pending or {}, ensure_ascii=False)[:800]
    system = (
        "你是企业问数系统的对话分流助手。只输出 JSON，不要 markdown。\n"
        "dialogue_act 取值：\n"
        "- chitchat：寒暄、能力说明、与数据无关闲聊\n"
        "- out_of_scope：明显非本系统数据域（写诗/编程/天气等）\n"
        "- clarify：像问数但缺关键槽（时间/指标/实体）或过糊\n"
        "- data_query：可执行的问数（有足够槽位）\n"
        "标准槽：time_range / metric / entity / scope / dimension\n"
        "原则：错答成本高于多问一轮；无时间且非「累计/总共」→ 倾向 clarify；"
        "无任何指标/度量意图 → clarify。\n"
        "若有 pending_clarification，优先判断本轮是补槽还是换题；"
        "补槽则合并进 resolved_question；换题则按新问句分流。\n"
        "输出字段：dialogue_act,confidence,resolved_question,missing_slots,"
        "filled_slots,clarify_question,clarify_options,chat_reply,reason\n"
    )
    user = (
        f"用户本轮问句：{question}\n\n"
        f"pending_clarification：{pending_text}\n\n"
        "请输出分流 JSON。"
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
        return _normalize_route(parsed, question=question)
    except Exception:
        return None
