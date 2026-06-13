"""
问句规划 LLM：输出 JSON plan（§11.7.3）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_sql import build_llm
from config.settings import Settings

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
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


def _normalize_plan(raw: dict[str, Any]) -> dict[str, Any]:
    """校验并补齐 plan 字段。"""
    complexity = str(raw.get("complexity") or "high").lower()
    if complexity not in ("low", "medium", "high"):
        complexity = "high"
    intent = str(raw.get("intent") or "open_query")
    steps = raw.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    normalized_steps: list[dict[str, Any]] = []
    for idx, step in enumerate(steps[:6], start=1):
        if not isinstance(step, dict):
            continue
        needs = step.get("needs_tool") or []
        if not isinstance(needs, list):
            needs = []
        normalized_steps.append(
            {
                "id": step.get("id") or idx,
                "goal": str(step.get("goal") or "").strip() or f"步骤 {idx}",
                "tables": step.get("tables") if isinstance(step.get("tables"), list) else [],
                "needs_tool": [str(t) for t in needs if t],
                "aggregation": step.get("aggregation"),
                "pivot_hint": step.get("pivot_hint"),
            }
        )
    sources = raw.get("sources") or ["meta:recall"]
    if not isinstance(sources, list):
        sources = ["meta:recall"]
    return {
        "complexity": complexity,
        "intent": intent,
        "steps": normalized_steps,
        "sources": [str(s) for s in sources],
    }


async def generate_plan_from_llm(
    *,
    settings: Settings,
    question: str,
    recall_summary: str,
) -> dict[str, Any] | None:
    """
    调用 LLM 生成问句分解 plan。

    Returns:
        规范化后的 plan dict；解析失败返回 None。
    """
    llm = build_llm(settings)
    system = (
        "你是企业问数系统的查询规划助手。"
        "根据用户问句与种子召回摘要，输出 JSON 计划，不要输出其它文字。"
        "complexity 取值 low/medium/high；复杂多维报表、多表 JOIN、动态列用 high。"
        "steps 至少 2 步（复杂问句）；每步 needs_tool 从以下选取："
        "describe_table, list_relations, get_join_path, search_metrics, "
        "search_field_values, search_sql_examples。"
    )
    user = (
        f"用户问句：{question}\n\n"
        f"种子召回摘要：\n{recall_summary}\n\n"
        "请输出 JSON，格式："
        '{"complexity":"high","intent":"multi_dim_report","steps":[{"id":1,'
        '"goal":"...","tables":[],"needs_tool":["describe_table"]}],'
        '"sources":["meta:recall"]}'
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed = _extract_json(content)
        if parsed:
            return _normalize_plan(parsed)
    except Exception:
        return None
    return None
