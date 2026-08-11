"""
Agent ReAct LLM：选择 tool 或结束 loop（§11.7.4 · 第 8 周）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.context_builder import _normalize_meta_table_name, _pick_candidate_tables
from app.agent.llm_client import complete_messages
from app.agent.plan_llm import _extract_json
from app.security.prompt_boundary import build_agent_system_preamble, wrap_untrusted
from config.settings import Settings

_AGENT_TOOLS = (
    "describe_table",
    "list_relations",
    "get_join_path",
    "search_metrics",
    "search_field_values",
    "search_sql_examples",
    "run_probe_sql",
    "search_code_artifacts",
    "get_code_artifact",
    "trace_code_flow",
    "link_artifact_to_meta",
    "ask_user_question",
    "submit_final_sql",
)


def _format_observations(observations: list[dict]) -> str:
    lines: list[str] = []
    for obs in observations[-8:]:
        tool = obs.get("tool")
        result = obs.get("result") or {}
        if result.get("error"):
            preview = f"error={result.get('error')}"
        elif "count" in result:
            preview = f"count={result['count']}"
        elif "column_count" in result:
            preview = f"columns={result['column_count']}"
        elif "rows" in result:
            preview = f"rows={len(result.get('rows') or [])}"
        else:
            preview = "ok"
        lines.append(f"- {tool}: {preview}")
    return "\n".join(lines) if lines else "（尚无观察）"


def _successful_described_tables(observations: list[dict]) -> set[str]:
    tables: set[str] = set()
    for obs in observations:
        if obs.get("tool") != "describe_table":
            continue
        result = obs.get("result") or {}
        if result.get("error"):
            continue
        table = result.get("table") or (obs.get("args") or {}).get("table")
        if table:
            tables.add(str(table).lower())
        else:
            tables.add("__any__")
    return tables


def _describe_table_done(default_tables: list[str], observations: list[dict]) -> bool:
    """describe_table 完成：已成功描述候选表，或已穷尽候选。"""
    if "__any__" in _successful_described_tables(observations):
        return True
    candidates = _pick_candidate_tables(default_tables, limit=5)
    if not candidates:
        return bool(_successful_described_tables(observations))
    successful = _successful_described_tables(observations)
    if successful.intersection(candidates):
        return True
    tried: set[str] = set()
    for obs in observations:
        if obs.get("tool") != "describe_table":
            continue
        args = obs.get("args") or {}
        result = obs.get("result") or {}
        table = str(args.get("table") or result.get("table") or "").lower()
        if table:
            tried.add(table)
    return bool(candidates) and tried.issuperset(set(candidates))


def _next_describe_table(default_tables: list[str], observations: list[dict]) -> str:
    candidates = _pick_candidate_tables(default_tables, limit=5)
    tried: set[str] = set()
    for obs in observations:
        if obs.get("tool") != "describe_table":
            continue
        args = obs.get("args") or {}
        result = obs.get("result") or {}
        table = _normalize_meta_table_name(str(args.get("table") or result.get("table") or ""))
        if table:
            tried.add(table)
    for candidate in candidates:
        if candidate not in tried:
            return candidate
    return candidates[0] if candidates else ""


def _tool_done(
    tool: str,
    observations: list[dict],
    *,
    default_tables: list[str],
) -> bool:
    if tool == "describe_table":
        return _describe_table_done(default_tables, observations)
    return any(o.get("tool") == tool for o in observations)


def _fallback_action(
    plan: dict[str, Any] | None,
    observations: list[dict],
    *,
    default_tables: list[str],
    question: str,
) -> dict[str, Any]:
    """LLM 不可用或解析失败时，按 plan.needs_tool 顺序执行未完成的工具。"""
    for step in (plan or {}).get("steps") or []:
        for tool in step.get("needs_tool") or []:
            if _tool_done(tool, observations, default_tables=default_tables):
                continue
            return {"action": "tool", "tool": tool, "args": _default_tool_args(tool, default_tables, question, observations)}
    return {"action": "finish"}


def _default_tool_args(
    tool: str,
    tables: list[str],
    question: str,
    observations: list[dict] | None = None,
) -> dict[str, Any]:
    observations = observations or []
    if tool == "describe_table":
        table = _next_describe_table(tables, observations)
        if table:
            return {"table": table}
    candidates = _pick_candidate_tables(tables, limit=5)
    if tool == "list_relations" and candidates:
        return {"table": candidates[0]}
    if tool == "get_join_path" and len(candidates) >= 2:
        return {"from_table": candidates[0], "to_table": candidates[1]}
    if tool in ("search_metrics", "search_field_values", "search_sql_examples", "search_code_artifacts"):
        return {"query": question}
    return {}


def _sanitize_tool_args(
    tool: str,
    args: dict[str, Any],
    *,
    default_tables: list[str],
    observations: list[dict],
    question: str,
) -> dict[str, Any]:
    if tool != "describe_table":
        return args
    table = str(args.get("table") or "")
    norm = _normalize_meta_table_name(table)
    candidates = _pick_candidate_tables(default_tables, limit=5)
    if norm and norm in candidates:
        return {"table": norm}
    return _default_tool_args(tool, default_tables, question, observations)


async def decide_agent_action(
    *,
    settings: Settings,
    question: str,
    plan: dict[str, Any] | None,
    observations: list[dict],
    default_tables: list[str],
    thinking_queue: Any | None = None,
) -> dict[str, Any]:
    """
    决定 Agent 下一步：调用 tool 或结束 loop。

    Returns:
        {"action": "tool"|"finish", "tool": str?, "args": dict?}
    """
    fallback = _fallback_action(plan, observations, default_tables=default_tables, question=question)
    plan_text = json.dumps(plan or {}, ensure_ascii=False)[:2000]
    obs_text = _format_observations(observations)
    system = (
        build_agent_system_preamble()
        + "你是企业问数 Agent，根据问句、规划与已有观察，选择下一步只读工具。"
        f"可用工具：{', '.join(_AGENT_TOOLS)}。"
        "输出 JSON：{\"action\":\"tool\",\"tool\":\"describe_table\",\"args\":{\"table\":\"表名\"}}"
        "或 {\"action\":\"finish\"} 表示信息足够可生成 SQL。"
        "或 {\"action\":\"ask_user\",\"tool\":\"ask_user_question\",\"args\":{\"reason\":\"...\",\"questions\":[...]}}"
        "当指标/实体仍歧义且无法安全出 SQL 时用 ask_user，禁止瞎猜 finish。"
        "禁止写库；run_probe_sql 仅用于 DISTINCT/COUNT 探查，须带 LIMIT。"
    )
    bounded_q = wrap_untrusted(
        "user_question",
        question,
        max_chars=2000,
        enabled=settings.prompt_boundary_enabled,
    )
    user = (
        f"问句：{bounded_q}\n\n"
        f"规划 plan：{plan_text}\n\n"
        f"已有观察：\n{obs_text}\n\n"
        "请输出下一步 JSON。"
    )
    try:
        content, _reasoning, _ti, _to = await complete_messages(
            settings,
            [SystemMessage(content=system), HumanMessage(content=user)],
            thinking_queue=thinking_queue,
        )
        parsed = _extract_json(content)
        if not parsed:
            return fallback
        action = str(parsed.get("action") or "").lower()
        if action in ("finish", "done", "submit_final_sql"):
            return {"action": "finish"}
        if action in ("ask_user", "ask_user_question"):
            args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
            return {"action": "ask_user", "tool": "ask_user_question", "args": args}
        tool = str(parsed.get("tool") or "").strip()
        if tool == "submit_final_sql":
            return {"action": "finish"}
        if tool == "ask_user_question":
            args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
            return {"action": "ask_user", "tool": "ask_user_question", "args": args}
        if tool not in _AGENT_TOOLS or tool == "submit_final_sql":
            return fallback
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        if not args:
            args = _default_tool_args(tool, default_tables, question, observations)
        else:
            args = _sanitize_tool_args(
                tool,
                args,
                default_tables=default_tables,
                observations=observations,
                question=question,
            )
        return {"action": "tool", "tool": tool, "args": args}
    except Exception:
        return fallback


def _extract_cte_sql(text: str) -> str | None:
    """从分步 SQL 输出提取 SELECT 或 WITH 语句。"""
    stripped = text.strip()
    block = re.search(r"```(?:sql)?\s*([\s\S]*?)```", stripped, re.IGNORECASE)
    candidate = block.group(1).strip() if block else stripped
    upper = candidate.upper()
    if upper.startswith("SELECT") or upper.startswith("WITH"):
        return candidate.rstrip(";").strip()
    match = re.search(r"((?:WITH|SELECT)[\s\S]+)", candidate, re.IGNORECASE)
    if match:
        return match.group(1).rstrip(";").strip()
    return None
