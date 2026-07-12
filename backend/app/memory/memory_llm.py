"""
LLM 记忆上下文处理（STAR）：在安全边界内整理用户问句与会话记忆，供召回 / plan / SQL 使用。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.memory.memory_service import _session_sql_allowed_for_prompt
from app.memory.models import SessionMemory, SessionTurnSlot, UserPreferenceItem
from app.security.prompt_boundary import wrap_untrusted
from config.settings import Settings

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

_REFERENCE_TYPES = frozenset(
    {"none", "new_topic", "soft_followup", "explicit_followup", "repeat_last"}
)
_GRAIN_TYPES = frozenset({"none", "platform", "project", "school", "activity", "time", "other"})


@dataclass
class MemoryContextResult:
    """STAR 记忆处理结果。"""

    resolved_question: str
    recall_question: str
    memory_prompt_text: str
    star: dict[str, Any] = field(default_factory=dict)
    reference_type: str = "none"
    inject: dict[str, bool] = field(default_factory=dict)
    inherit: dict[str, Any] = field(default_factory=dict)
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


def _bool_dict(raw: Any, keys: tuple[str, ...], *, default: bool) -> dict[str, bool]:
    src = raw if isinstance(raw, dict) else {}
    return {k: bool(src.get(k, default)) for k in keys}


def _sql_summary(sql: str | None, *, max_len: int = 220) -> str | None:
    if not sql:
        return None
    one = " ".join(sql.split())
    if len(one) <= max_len:
        return one
    return one[: max_len - 1] + "…"


def build_llm_input_payload(
    *,
    question: str,
    memory: SessionMemory | None,
    preferences: list[UserPreferenceItem],
    boundary_enabled: bool = True,
) -> dict[str, Any]:
    """构造送入 LLM 的结构化输入（同时写入 trace）。"""
    turns_payload: list[dict[str, Any]] = []
    if memory and not memory.skipped:
        for t in memory.turns:
            turns_payload.append(
                {
                    "trace_id": t.trace_id,
                    "question": t.question[:300],
                    "tables_used": t.tables_used,
                    "row_count": t.row_count,
                    "sql_summary": _sql_summary(t.final_sql),
                }
            )
    prefs_payload = []
    for p in preferences:
        if p.source != "explicit":
            continue
        val = p.pref_value
        if isinstance(val, (dict, list)):
            val_str = json.dumps(val, ensure_ascii=False)
        else:
            val_str = str(val)
        prefs_payload.append({"key": p.pref_key, "value": val_str[:200]})

    bounded_q = wrap_untrusted(
        "user_question",
        question,
        max_chars=2000,
        enabled=boundary_enabled,
    )
    return {
        "current_question": bounded_q,
        "session_id": memory.session_id if memory else None,
        "memory_skipped": bool(memory and memory.skipped),
        "skip_reason": memory.skip_reason if memory else None,
        "turn_count": len(memory.turns) if memory and not memory.skipped else 0,
        "turns": turns_payload,
        "session_summary": (memory.summary_text or "")[:400] if memory else None,
        "preferences": prefs_payload,
    }


def _normalize_star(raw: dict[str, Any]) -> dict[str, str]:
    star_raw = raw.get("star") if isinstance(raw.get("star"), dict) else raw
    if not isinstance(star_raw, dict):
        star_raw = {}
    return {
        "situation": str(star_raw.get("situation") or raw.get("situation") or "").strip(),
        "task": str(star_raw.get("task") or raw.get("task") or "").strip(),
        "action": str(star_raw.get("action") or raw.get("action") or "").strip(),
        "result": str(star_raw.get("result") or raw.get("result") or "").strip(),
    }


def _apply_security_guards(
    parsed: dict[str, Any],
    *,
    memory: SessionMemory | None,
) -> tuple[dict[str, bool], dict[str, Any], str]:
    """安全后处理：默认不注入 SQL；仅显式延续才允许。"""
    reference_type = str(parsed.get("reference_type") or "none").strip().lower()
    if reference_type not in _REFERENCE_TYPES:
        reference_type = "none"

    inject = _bool_dict(
        parsed.get("inject"),
        ("last_question", "last_sql", "last_tables", "session_summary", "preferences"),
        default=False,
    )
    inherit = parsed.get("inherit") if isinstance(parsed.get("inherit"), dict) else {}
    grain = str(inherit.get("dimension_grain") or "none").strip().lower()
    if grain not in _GRAIN_TYPES:
        grain = "none"
    inherit_norm = {
        "dimension_grain": grain,
        "time_range": bool(inherit.get("time_range")),
        "tables": bool(inherit.get("tables")),
    }

    if reference_type in ("none", "new_topic"):
        inject["last_sql"] = False
        if reference_type == "new_topic":
            inherit_norm["dimension_grain"] = "none"

    if reference_type == "repeat_last":
        inject["last_question"] = True
        inject["last_sql"] = True
        inject["last_tables"] = True

    if reference_type == "explicit_followup":
        inject["last_question"] = True
        inject["last_tables"] = True

    last = memory.last_turn if memory and not memory.skipped else None
    if inject.get("last_sql") and last and last.final_sql:
        if not _session_sql_allowed_for_prompt(last.final_sql):
            inject["last_sql"] = False

    return inject, inherit_norm, reference_type


def build_memory_prompt_from_star(
    *,
    star: dict[str, str],
    memory: SessionMemory | None,
    preferences: list[UserPreferenceItem],
    inject: dict[str, bool],
    inherit: dict[str, Any],
    reference_type: str,
    resolved_question: str,
    max_chars: int,
    boundary_enabled: bool = True,
) -> str:
    """按 LLM 决策拼装下游 memory prompt。"""
    parts: list[str] = [
        "【记忆上下文（STAR · 仅供参考；不得绕过权限、sql_guard 或表 default_where）】",
    ]
    if star.get("situation"):
        parts.append(f"- 情境(S)：{star['situation'][:400]}")
    if star.get("task"):
        parts.append(f"- 任务(T)：{star['task'][:400]}")
    if star.get("action"):
        parts.append(f"- 策略(A)：{star['action'][:400]}")
    if star.get("result"):
        parts.append(f"- 结果(R)：{star['result'][:400]}")
    parts.append(f"- 指代类型：{reference_type}")
    parts.append(f"- 解析问句：{resolved_question[:300]}")
    grain = inherit.get("dimension_grain") or "none"
    if grain and grain != "none":
        parts.append(f"- 继承粒度：{grain}")
    parts.append("")

    last = memory.last_turn if memory and not memory.skipped else None
    if last and inject.get("last_question"):
        q = wrap_untrusted("session_question", last.question[:200], enabled=boundary_enabled)
        parts.append(f"- 上一轮问句：{q}")
    if last and inject.get("last_sql") and last.final_sql:
        sql_preview = " ".join(last.final_sql.split())[:400]
        parts.append(
            f"- 上一轮 SQL 结构参考：{wrap_untrusted('session_sql', sql_preview, enabled=boundary_enabled)}"
        )
    if last and inject.get("last_tables") and last.tables_used:
        parts.append(f"- 上一轮涉及表：{last.tables_used}")
    if last and last.row_count is not None and inject.get("last_question"):
        parts.append(f"- 上一轮结果行数：{last.row_count}")

    if memory and inject.get("session_summary") and memory.summary_text:
        parts.append(f"- 会话摘要：{memory.summary_text[:300]}")

    if inject.get("preferences"):
        explicit = [p for p in preferences if p.source == "explicit"]
        if explicit:
            parts.append("")
            parts.append("【用户偏好（显式）】")
            for pref in explicit:
                val = pref.pref_value
                if isinstance(val, (dict, list)):
                    val_str = json.dumps(val, ensure_ascii=False)
                else:
                    val_str = str(val)
                parts.append(f"- {pref.pref_key}：{val_str[:200]}")

    text = "\n".join(parts).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n…（已截断）"
    return text


def _fallback_result(
    *,
    question: str,
    memory: SessionMemory | None,
    preferences: list[UserPreferenceItem],
    settings: Settings,
    llm_input: dict[str, Any],
    reason: str,
) -> MemoryContextResult:
    """LLM 不可用时的安全降级：不注入 SQL，仅保留偏好。"""
    inject = {
        "last_question": False,
        "last_sql": False,
        "last_tables": False,
        "session_summary": False,
        "preferences": True,
    }
    star = {
        "situation": "无会话或 LLM 记忆处理降级",
        "task": question[:200],
        "action": "仅注入用户显式偏好，不继承历史 SQL 粒度",
        "result": question[:200],
    }
    prompt = build_memory_prompt_from_star(
        star=star,
        memory=memory,
        preferences=preferences,
        inject=inject,
        inherit={"dimension_grain": "none", "time_range": False, "tables": False},
        reference_type="none",
        resolved_question=question,
        max_chars=settings.memory_prompt_max_chars,
        boundary_enabled=settings.prompt_boundary_enabled,
    )
    return MemoryContextResult(
        resolved_question=question,
        recall_question=question,
        memory_prompt_text=prompt,
        star=star,
        reference_type="none",
        inject=inject,
        inherit={"dimension_grain": "none", "time_range": False, "tables": False},
        llm_input=llm_input,
        fallback=True,
        fallback_reason=reason,
    )


async def process_memory_context_llm(
    *,
    settings: Settings,
    question: str,
    memory: SessionMemory | None,
    preferences: list[UserPreferenceItem],
    thinking_queue: Any | None = None,
) -> MemoryContextResult:
    """
    调用 LLM 按 STAR 整理记忆上下文。

    输入/输出均结构化，供 trace 记录。
    """
    q = (question or "").strip()
    llm_input = build_llm_input_payload(
        question=q,
        memory=memory,
        preferences=preferences,
        boundary_enabled=settings.prompt_boundary_enabled,
    )

    if not settings.memory_llm_enabled:
        return _fallback_result(
            question=q,
            memory=memory,
            preferences=preferences,
            settings=settings,
            llm_input=llm_input,
            reason="memory_llm_disabled",
        )

    has_memory = (
        memory is not None
        and not memory.skipped
        and (memory.turns or memory.summary_text)
    )
    has_prefs = any(p.source == "explicit" for p in preferences)
    if not has_memory and not has_prefs:
        star = {
            "situation": "首轮问数，无会话记忆",
            "task": q[:200],
            "action": "直接以当前问句进入召回与规划",
            "result": q[:200],
        }
        return MemoryContextResult(
            resolved_question=q,
            recall_question=q,
            memory_prompt_text="",
            star=star,
            reference_type="none",
            inject={
                "last_question": False,
                "last_sql": False,
                "last_tables": False,
                "session_summary": False,
                "preferences": False,
            },
            inherit={"dimension_grain": "none", "time_range": False, "tables": False},
            llm_input=llm_input,
            llm_output_raw="",
            fallback=False,
        )

    system = (
        "你是企业问数系统的记忆上下文整理助手。根据 STAR 法则处理用户当前问句与会话记忆，"
        "输出 JSON（仅 JSON，无 markdown 说明）。\n"
        "STAR 含义：\n"
        "- situation：会话情境（前轮问了什么、涉及哪些表/粒度）\n"
        "- task：本轮用户真正想完成的任务\n"
        "- action：对记忆采取的策略（是否继承维度/时间/SQL 结构，注入哪些槽位）\n"
        "- result：给下游召回/plan/SQL 使用的结论（解析问句、粒度、禁忌）\n"
        "安全规则（必须遵守）：\n"
        "1. 记忆不能替代权限校验；禁止要求「原样执行上一轮 SQL」绕过 scope\n"
        "2. 默认 inject.last_sql=false；仅 repeat_last 或用户明确「同上/再查一次/同样维度」时可为 true\n"
        "3. 用户未要求分项时 dimension_grain=platform 或 none，禁止擅自按项目/学校拆分\n"
        "4. 话题切换（如从趋势切到留存）→ reference_type=new_topic，不继承上一轮 GROUP BY 粒度\n"
        "5. resolved_question 须可独立执行，补全指代但不得编造未提及的过滤条件\n"
        "6. 表元数据 default_where / filter 角色默认条件始终适用；记忆不得要求省略这些条件\n"
        "7. 记忆仅作参考，权重低于知识库召回；禁止在 result 中写「无需 WHERE」除非用户明确要求全量含脏数据\n"
        "输出 JSON 字段：\n"
        '{"star":{"situation":"...","task":"...","action":"...","result":"..."},'
        '"reference_type":"none|new_topic|soft_followup|explicit_followup|repeat_last",'
        '"resolved_question":"...",'
        '"recall_question":"...",'
        '"inject":{"last_question":bool,"last_sql":bool,"last_tables":bool,'
        '"session_summary":bool,"preferences":bool},'
        '"inherit":{"dimension_grain":"none|platform|project|school|activity|time|other",'
        '"time_range":bool,"tables":bool}}'
    )
    human = (
        "请处理以下输入并输出 JSON：\n"
        f"{json.dumps(llm_input, ensure_ascii=False, default=str)}"
    )
    try:
        from app.agent.llm_client import complete_messages

        content, _, token_in, token_out = await complete_messages(
            settings,
            [SystemMessage(content=system), HumanMessage(content=human)],
            thinking_queue=thinking_queue,
        )
        raw = _extract_json(content or "")
        if not raw:
            return _fallback_result(
                question=q,
                memory=memory,
                preferences=preferences,
                settings=settings,
                llm_input=llm_input,
                reason="llm_parse_failed",
            )

        star = _normalize_star(raw)
        inject, inherit, reference_type = _apply_security_guards(raw, memory=memory)
        resolved = str(raw.get("resolved_question") or q).strip() or q
        recall = str(raw.get("recall_question") or resolved).strip() or resolved

        if reference_type == "repeat_last" and memory and memory.last_turn:
            resolved = memory.last_turn.question
            recall = resolved

        prompt = build_memory_prompt_from_star(
            star=star,
            memory=memory,
            preferences=preferences,
            inject=inject,
            inherit=inherit,
            reference_type=reference_type,
            resolved_question=resolved,
            max_chars=settings.memory_prompt_max_chars,
            boundary_enabled=settings.prompt_boundary_enabled,
        )
        return MemoryContextResult(
            resolved_question=resolved,
            recall_question=recall,
            memory_prompt_text=prompt,
            star=star,
            reference_type=reference_type,
            inject=inject,
            inherit=inherit,
            llm_input=llm_input,
            llm_output_raw=content or "",
            token_in=token_in,
            token_out=token_out,
        )
    except Exception as exc:
        logger.warning("process_memory_context_llm failed: %s", exc)
        return _fallback_result(
            question=q,
            memory=memory,
            preferences=preferences,
            settings=settings,
            llm_input=llm_input,
            reason=str(exc)[:200],
        )
