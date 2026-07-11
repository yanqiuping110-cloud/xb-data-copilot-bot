"""
L1 样例 LLM 精选：结合问句、上下文与 STAR 从知识库候选中选出 0~N 条。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.context_builder import MergedRecallContext
from app.ask.l1_service import L1ExampleCandidate
from app.agent.llm_client import complete_messages
from config.settings import Settings

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


@dataclass
class L1SelectResult:
    selected: list[L1ExampleCandidate]
    llm_input: dict[str, Any] = field(default_factory=dict)
    llm_output_raw: str = ""
    token_in: int | None = None
    token_out: int | None = None
    fallback: bool = False
    fallback_reason: str | None = None


def _extract_json(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    block = _JSON_BLOCK_RE.search(stripped)
    candidate = block.group(1).strip() if block else stripped
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(candidate[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _recall_summary(merged: MergedRecallContext | None) -> str:
    if merged is None:
        return "（无召回）"
    lines = [
        f"召回模式: {merged.recall_mode}",
        f"关键词: {', '.join(merged.keywords) or '（整句）'}",
        f"候选表: {', '.join(merged.table_names[:5]) or '（无）'}",
    ]
    if merged.metrics:
        lines.append(
            "指标: " + ", ".join(f"{m.metric_code}" for m in merged.metrics[:3])
        )
    return "\n".join(lines)


def _star_summary(star: dict | None, reference_type: str | None) -> str:
    if not star:
        return f"指代类型: {reference_type or 'none'}"
    parts = []
    for key, label in (
        ("situation", "S"),
        ("task", "T"),
        ("action", "A"),
        ("result", "R"),
    ):
        val = star.get(key)
        if val:
            parts.append(f"{label}: {str(val)[:200]}")
    if reference_type:
        parts.append(f"指代类型: {reference_type}")
    return "\n".join(parts) if parts else f"指代类型: {reference_type or 'none'}"


def _candidate_brief(ex: L1ExampleCandidate) -> str:
    desc = f"；说明={ex.description[:120]}" if ex.description else ""
    return f"[id={ex.id}] 问句={ex.question_pattern}{desc}；召回分={ex.recall_score:.3f}"


def _apply_selection(
    candidates: list[L1ExampleCandidate],
    parsed: dict[str, Any],
    *,
    max_select: int,
) -> list[L1ExampleCandidate]:
    by_id = {c.id: c for c in candidates}
    selected_ids = parsed.get("selected_ids") or parsed.get("selectedIds") or []
    reasons = parsed.get("reasons") or {}
    if not isinstance(selected_ids, list):
        return []
    out: list[L1ExampleCandidate] = []
    for raw_id in selected_ids[:max_select]:
        try:
            eid = int(raw_id)
        except (TypeError, ValueError):
            continue
        base = by_id.get(eid)
        if base is None:
            continue
        reason = reasons.get(str(eid)) or reasons.get(eid)
        out.append(
            L1ExampleCandidate(
                id=base.id,
                question_pattern=base.question_pattern,
                sql_text=base.sql_text,
                description=base.description,
                recall_score=base.recall_score,
                select_reason=str(reason)[:200] if reason else None,
            )
        )
    return out


async def select_l1_examples_llm(
    *,
    settings: Settings,
    question: str,
    recall_question: str,
    candidates: list[L1ExampleCandidate],
    context_text: str,
    merged: MergedRecallContext | None,
    memory_star: dict | None,
    reference_type: str | None,
    thinking_queue: Any | None = None,
) -> L1SelectResult:
    """LLM 从知识库候选中精选 0~max 条 L1 样例。"""
    max_select = settings.l1_select_max
    llm_input = {
        "question": question,
        "recall_question": recall_question,
        "candidate_count": len(candidates),
        "max_select": max_select,
        "reference_type": reference_type,
        "star": memory_star,
    }

    if not candidates:
        return L1SelectResult(selected=[], llm_input=llm_input, fallback_reason="no_candidates")

    if not settings.l1_select_llm_enabled:
        return L1SelectResult(
            selected=[],
            llm_input=llm_input,
            fallback=True,
            fallback_reason="l1_select_llm_disabled",
        )

    context_preview = (context_text or "")[: settings.l1_select_context_max_chars]
    candidate_lines = "\n".join(_candidate_brief(c) for c in candidates)

    system = (
        "你是企业问数系统的 L1 样例精选助手。根据用户问句、STAR 记忆、召回上下文，"
        "从候选 L1 SQL 样例中选出 0~{max_select} 条真正有助于本轮规划/SQL 的样例。\n"
        "仅输出 JSON：{{\"selected_ids\": [id...], \"reasons\": {{\"id\": \"选用理由\"}}}}\n"
        "规则：\n"
        "- 可以一条都不选（selected_ids 为空数组）\n"
        "- 最多选 {max_select} 条\n"
        "- reference_type=new_topic 时，勿选与当前问句业务/表无关的历史样例\n"
        "- 样例仅作软参考，勿强行匹配不相关问法\n"
        "- selected_ids 必须来自候选列表中的 id\n"
    ).format(max_select=max_select)

    user = "\n".join(
        [
            f"用户问句：{question}",
            f"召回问句：{recall_question or question}",
            "",
            "STAR / 指代：",
            _star_summary(memory_star, reference_type),
            "",
            "召回摘要：",
            _recall_summary(merged),
            "",
            "问数上下文（截断）：",
            context_preview or "（无）",
            "",
            "候选 L1 样例：",
            candidate_lines,
        ]
    )

    try:
        content, _reasoning, ti, to = await complete_messages(
            settings,
            [SystemMessage(content=system), HumanMessage(content=user)],
            thinking_queue=thinking_queue,
        )
        parsed = _extract_json(content or "")
        if parsed is None:
            return L1SelectResult(
                selected=[],
                llm_input=llm_input,
                llm_output_raw=content or "",
                token_in=ti,
                token_out=to,
                fallback=True,
                fallback_reason="json_parse_failed",
            )
        selected = _apply_selection(candidates, parsed, max_select=max_select)
        return L1SelectResult(
            selected=selected,
            llm_input=llm_input,
            llm_output_raw=content or "",
            token_in=ti,
            token_out=to,
        )
    except Exception as exc:
        logger.warning("L1 select LLM failed: %s", exc)
        return L1SelectResult(
            selected=[],
            llm_input=llm_input,
            fallback=True,
            fallback_reason=str(exc)[:200],
        )
