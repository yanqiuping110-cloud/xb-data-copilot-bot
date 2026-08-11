"""
AskUserQuestion 载荷裁剪与扁平兼容。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4


def new_clarification_thread_id() -> str:
    return f"clr_{uuid4().hex[:16]}"


def clip_ask_user_question(
    payload: dict[str, Any] | None,
    *,
    max_questions: int = 2,
    max_options: int = 4,
) -> dict[str, Any] | None:
    """裁剪 AskUserQuestion：问题 ≤ max(硬顶4)、每题选项 ≤ max_options。"""
    if not payload or not isinstance(payload, dict):
        return None
    hard_q = min(max(1, max_questions), 4)
    hard_o = min(max(1, max_options), 4)
    questions_raw = payload.get("questions") or []
    if not isinstance(questions_raw, list):
        questions_raw = []
    questions: list[dict[str, Any]] = []
    for q in questions_raw[:hard_q]:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or f"q{len(questions) + 1}").strip() or f"q{len(questions) + 1}"
        prompt = str(q.get("prompt") or q.get("question") or "").strip()
        if not prompt:
            continue
        opts_raw = q.get("options") or []
        if not isinstance(opts_raw, list):
            opts_raw = []
        options: list[dict[str, Any]] = []
        saw_recommended = False
        for opt in opts_raw[:hard_o]:
            if not isinstance(opt, dict):
                continue
            label = str(opt.get("label") or "").strip()
            if not label:
                continue
            oid = str(opt.get("id") or label).strip() or label
            recommended = bool(opt.get("recommended")) and not saw_recommended
            if recommended:
                saw_recommended = True
            options.append({"id": oid, "label": label, "recommended": recommended})
        questions.append(
            {
                "id": qid,
                "prompt": prompt,
                "allow_free_text": bool(q.get("allow_free_text", True)),
                "options": options,
            }
        )
    if not questions:
        return None
    return {
        "title": str(payload.get("title") or "还需要确认一下").strip() or "还需要确认一下",
        "reason": str(payload.get("reason") or "").strip() or None,
        "questions": questions,
    }


def build_ask_user_from_slots(
    *,
    missing_slots: list[str],
    filled_slots: dict[str, Any] | None = None,
    clarify_question: str | None = None,
    clarify_options: list[str] | None = None,
    metric_candidates: list[str] | None = None,
    reason: str | None = None,
    max_questions: int = 2,
    max_options: int = 4,
) -> dict[str, Any]:
    """按缺槽组装 AskUserQuestion（无 LLM 时的默认载荷）。"""
    filled = filled_slots or {}
    entity = str(filled.get("entity") or "").strip()
    questions: list[dict[str, Any]] = []
    missing = list(missing_slots or [])

    if "time_range" in missing:
        questions.append(
            {
                "id": "time_range",
                "prompt": "想看哪个时间范围？",
                "allow_free_text": True,
                "options": [
                    {"id": "7d", "label": "近7天", "recommended": True},
                    {"id": "month", "label": "本月"},
                    {"id": "year", "label": "本年"},
                ],
            }
        )
    if "metric" in missing:
        defaults = metric_candidates or ["数量", "趋势", "占比"]
        opts: list[dict[str, Any]] = []
        for i, name in enumerate(defaults[: max_options - 1]):
            opts.append(
                {
                    "id": f"m{i}",
                    "label": name,
                    "recommended": i == 0,
                }
            )
        questions.append(
            {
                "id": "metric",
                "prompt": "关注哪个指标？",
                "allow_free_text": True,
                "options": opts,
            }
        )
    if "entity" in missing and not entity:
        questions.append(
            {
                "id": "entity",
                "prompt": "想看哪个对象或维度？",
                "allow_free_text": True,
                "options": [],
            }
        )
    if "scope" in missing:
        questions.append(
            {
                "id": "scope",
                "prompt": "统计范围是？",
                "allow_free_text": True,
                "options": [
                    {"id": "default", "label": "默认范围", "recommended": True},
                    {"id": "all", "label": "全部"},
                ],
            }
        )
    if not questions:
        opts = [{"id": f"o{i}", "label": o, "recommended": i == 0} for i, o in enumerate((clarify_options or [])[:max_options])]
        questions.append(
            {
                "id": "general",
                "prompt": clarify_question or "请补充查询条件（时间范围、指标等）",
                "allow_free_text": True,
                "options": opts,
            }
        )

    reason_text = reason
    if not reason_text and entity:
        reason_text = f"已识别「{entity}」，但还需要补充信息"
    elif not reason_text:
        reason_text = "问题信息不完整，需要补充后再查询"

    return clip_ask_user_question(
        {
            "title": "还需要确认一下",
            "reason": reason_text,
            "questions": questions,
        },
        max_questions=max_questions,
        max_options=max_options,
    ) or {
        "title": "还需要确认一下",
        "reason": reason_text,
        "questions": [
            {
                "id": "general",
                "prompt": clarify_question or "请补充查询条件",
                "allow_free_text": True,
                "options": [],
            }
        ],
    }


def flatten_ask_user(payload: dict[str, Any] | None) -> tuple[str | None, list[str]]:
    """从 AskUserQuestion 提取扁平 question + options（P0 兼容）。"""
    if not payload:
        return None, []
    questions = payload.get("questions") or []
    if not questions:
        return None, []
    prompts = [str(q.get("prompt") or "").strip() for q in questions if isinstance(q, dict)]
    prompts = [p for p in prompts if p]
    question = "；".join(prompts) if prompts else None
    options: list[str] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        for opt in q.get("options") or []:
            if isinstance(opt, dict) and opt.get("label"):
                label = str(opt["label"]).strip()
                if label and label not in options:
                    options.append(label)
    return question, options


def clarification_payload_dict(
    *,
    ask_user: dict[str, Any] | None,
    missing_slots: list[str] | None = None,
    partial_question: str | None = None,
    thread_id: str | None = None,
    clarify_question: str | None = None,
    clarify_options: list[str] | None = None,
) -> dict[str, Any]:
    """构造写入 state / AskResponse 的 clarification dict。"""
    flat_q, flat_opts = flatten_ask_user(ask_user)
    q = clarify_question or flat_q
    opts = clarify_options if clarify_options is not None else (flat_opts or None)
    out: dict[str, Any] = {
        "question": q,
        "missing_slots": list(missing_slots or []),
        "options": opts,
        "partial_question": partial_question,
        "title": (ask_user or {}).get("title") if ask_user else None,
        "reason": (ask_user or {}).get("reason") if ask_user else None,
        "questions": (ask_user or {}).get("questions") if ask_user else None,
        "thread_id": thread_id,
    }
    return out


def answers_to_text(answers: list[dict[str, Any]] | None, ask_user: dict[str, Any] | None) -> str:
    """将结构化作答转为自然语言补丁，供问句合并。"""
    if not answers:
        return ""
    label_by_id: dict[str, str] = {}
    for q in (ask_user or {}).get("questions") or []:
        if not isinstance(q, dict):
            continue
        for opt in q.get("options") or []:
            if isinstance(opt, dict) and opt.get("id"):
                label_by_id[str(opt["id"])] = str(opt.get("label") or opt["id"])
    parts: list[str] = []
    for ans in answers:
        if not isinstance(ans, dict):
            continue
        free = str(ans.get("free_text") or "").strip()
        if free:
            parts.append(free)
            continue
        oid = str(ans.get("option_id") or "").strip()
        if oid:
            parts.append(label_by_id.get(oid, oid))
    return "，".join(parts)
