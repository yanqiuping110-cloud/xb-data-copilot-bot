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

_SEARCH_TOOLS = frozenset(
    {
        "search_metrics",
        "search_field_values",
        "search_sql_examples",
        "search_code_artifacts",
    }
)


def _fp_table(name: Any) -> str:
    """指纹用表名：小写 + 去 schema，不过滤 PascalCase（避免漏去重）。"""
    raw = str(name or "").strip()
    if not raw:
        return ""
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    return raw.lower()


def _norm_query(value: Any, *, max_len: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return text[:max_len]


def _norm_sql_fingerprint(sql: Any) -> str:
    text = re.sub(r"\s+", " ", str(sql or "").strip().lower())
    return text[:240]


def tool_call_fingerprint(tool: str, args: dict[str, Any] | None) -> str:
    """
    工具调用指纹：相同语义参数视为同一次调用，用于硬去重。

    describe/list 按表；join 按端点无序对；search 按 query；probe 按 SQL。
    """
    name = str(tool or "").strip()
    args = args or {}
    if name == "describe_table":
        table = _fp_table(args.get("table"))
        return f"describe_table|{table}" if table else "describe_table|"
    if name == "list_relations":
        table = _fp_table(args.get("table"))
        return f"list_relations|{table}" if table else "list_relations|"
    if name == "get_join_path":
        a = _fp_table(args.get("from_table"))
        b = _fp_table(args.get("to_table"))
        pair = "|".join(sorted(x for x in (a, b) if x))
        return f"get_join_path|{pair}" if pair else "get_join_path|"
    if name in _SEARCH_TOOLS:
        return f"{name}|{_norm_query(args.get('query') or args.get('keyword'))}"
    if name == "run_probe_sql":
        return f"run_probe_sql|{_norm_sql_fingerprint(args.get('sql'))}"
    if name == "get_code_artifact":
        return f"get_code_artifact|{args.get('artifact_id')}"
    if name == "trace_code_flow":
        return f"trace_code_flow|{_norm_query(args.get('symbol_or_path') or args.get('query'), max_len=160)}"
    if name == "link_artifact_to_meta":
        return f"link_artifact_to_meta|{args.get('artifact_id')}"
    # 其余工具：tool + 稳定序列化参数
    try:
        payload = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        payload = str(args)
    return f"{name}|{_norm_query(payload, max_len=200)}"


def observation_fingerprints(observations: list[dict]) -> set[str]:
    """已执行（含失败）的工具调用指纹集合。"""
    out: set[str] = set()
    for obs in observations:
        tool = str(obs.get("tool") or "").strip()
        if not tool or tool in ("ask_user_question", "submit_final_sql"):
            continue
        fp = tool_call_fingerprint(tool, obs.get("args") if isinstance(obs.get("args"), dict) else {})
        if fp.endswith("|") and tool in ("describe_table", "list_relations", "get_join_path"):
            # 无关键参数的空指纹不参与去重，避免误伤
            continue
        out.add(fp)
    return out


def is_duplicate_tool_call(
    tool: str,
    args: dict[str, Any] | None,
    observations: list[dict],
) -> bool:
    """是否与历史 observation 指纹冲突。"""
    fp = tool_call_fingerprint(tool, args)
    if fp.endswith("|") and tool in ("describe_table", "list_relations", "get_join_path"):
        return False
    return fp in observation_fingerprints(observations)


def _format_args_brief(tool: str, args: dict[str, Any] | None) -> str:
    args = args or {}
    if tool == "describe_table" or tool == "list_relations":
        t = args.get("table")
        return f"table={t}" if t else ""
    if tool == "get_join_path":
        return f"from={args.get('from_table')} to={args.get('to_table')}"
    if tool in _SEARCH_TOOLS:
        q = str(args.get("query") or args.get("keyword") or "")
        return f"query={q[:60]}" if q else ""
    if tool == "run_probe_sql":
        sql = str(args.get("sql") or "")
        return f"sql={sql[:60]}" if sql else ""
    parts = [f"{k}={args[k]}" for k in list(args)[:3] if args.get(k) is not None]
    return " ".join(parts)


def _format_observations(observations: list[dict]) -> str:
    lines: list[str] = []
    for obs in observations[-8:]:
        tool = str(obs.get("tool") or "")
        args = obs.get("args") if isinstance(obs.get("args"), dict) else {}
        result = obs.get("result") or {}
        if result.get("error"):
            preview = f"error={result.get('error')}"
        elif result.get("skipped") == "duplicate":
            preview = "skipped=duplicate"
        elif "count" in result:
            preview = f"count={result['count']}"
        elif "column_count" in result:
            preview = f"columns={result['column_count']}"
        elif "rows" in result:
            preview = f"rows={len(result.get('rows') or [])}"
        else:
            preview = "ok"
        brief = _format_args_brief(tool, args)
        if brief:
            lines.append(f"- {tool}({brief}): {preview}")
        else:
            lines.append(f"- {tool}: {preview}")
    body = "\n".join(lines) if lines else "（尚无观察）"
    fps = sorted(observation_fingerprints(observations))
    if not fps:
        return body
    ban = "、".join(fps[:12])
    if len(fps) > 12:
        ban += "…"
    return f"{body}\n【禁止重复调用】已执行指纹：{ban}"


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


def _tried_describe_tables(observations: list[dict]) -> set[str]:
    """已尝试过的表（成功或失败都算，禁止同表重复 describe）。"""
    tried: set[str] = set()
    for obs in observations:
        if obs.get("tool") != "describe_table":
            continue
        args = obs.get("args") or {}
        result = obs.get("result") or {}
        table = _normalize_meta_table_name(str(args.get("table") or result.get("table") or ""))
        if table:
            tried.add(table)
    return tried


def _tried_list_relation_tables(observations: list[dict]) -> set[str]:
    tried: set[str] = set()
    for obs in observations:
        if obs.get("tool") != "list_relations":
            continue
        args = obs.get("args") or {}
        table = _normalize_meta_table_name(str(args.get("table") or ""))
        if table:
            tried.add(table)
    return tried


def _tried_join_pairs(observations: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for obs in observations:
        if obs.get("tool") != "get_join_path":
            continue
        args = obs.get("args") or {}
        a = _normalize_meta_table_name(str(args.get("from_table") or ""))
        b = _normalize_meta_table_name(str(args.get("to_table") or ""))
        if a and b:
            pairs.add(tuple(sorted((a, b))))
    return pairs


def _next_list_relations_table(
    default_tables: list[str],
    observations: list[dict],
) -> str:
    tried = _tried_list_relation_tables(observations)
    for candidate in _pick_candidate_tables(default_tables, limit=5):
        if candidate not in tried:
            return candidate
    return ""


def _next_join_path_args(
    default_tables: list[str],
    observations: list[dict],
) -> dict[str, str]:
    candidates = _pick_candidate_tables(default_tables, limit=5)
    tried = _tried_join_pairs(observations)
    for i, a in enumerate(candidates):
        for b in candidates[i + 1 :]:
            pair = tuple(sorted((a, b)))
            if pair not in tried:
                return {"from_table": a, "to_table": b}
    return {}


def _plan_needs_tools(plan: dict[str, Any] | None) -> list[str]:
    """按 plan.steps.needs_tool 收集工具清单（去重保序）。"""
    tools: list[str] = []
    for step in (plan or {}).get("steps") or []:
        if not isinstance(step, dict):
            continue
        for tool in step.get("needs_tool") or []:
            name = str(tool or "").strip()
            if name and name not in tools:
                tools.append(name)
    return tools


def _plan_describe_targets(
    plan: dict[str, Any] | None,
    default_tables: list[str],
) -> list[str]:
    """
    需要 describe 的表：plan 锚点/步骤表/metric_groups，再回落到候选表。

    不同表各一次；同表不重复。无明确目标时只取 1 张候选表，避免把 needs_tool
    里的一次 describe_table 扩成扫全库。
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(name: Any) -> None:
        norm = _normalize_meta_table_name(str(name or ""))
        if not norm or norm in seen:
            return
        seen.add(norm)
        ordered.append(norm)

    if isinstance(plan, dict):
        _add(plan.get("anchor_table"))
        for step in plan.get("steps") or []:
            if not isinstance(step, dict):
                continue
            for table in step.get("tables") or []:
                _add(table)
        for group in plan.get("metric_groups") or []:
            if not isinstance(group, dict):
                continue
            _add(group.get("anchor_table"))
            for table in group.get("source_tables") or []:
                _add(table)

    candidates = _pick_candidate_tables(default_tables, limit=5)
    cand_set = set(candidates)
    in_candidates = [t for t in ordered if t in cand_set]
    if in_candidates:
        return in_candidates[:5]
    if ordered:
        return ordered[:5]
    return candidates[:1]


def _describe_table_done(
    default_tables: list[str],
    observations: list[dict],
    *,
    plan: dict[str, Any] | None = None,
) -> bool:
    """describe_table 完成：目标表均已尝试（每张至多一次），或已有无表名成功观察。"""
    if "__any__" in _successful_described_tables(observations):
        return True
    targets = _plan_describe_targets(plan, default_tables)
    if not targets:
        return bool(_successful_described_tables(observations))
    tried = _tried_describe_tables(observations)
    return all(t in tried for t in targets)


def _next_describe_table(
    default_tables: list[str],
    observations: list[dict],
    *,
    plan: dict[str, Any] | None = None,
) -> str:
    targets = _plan_describe_targets(plan, default_tables)
    tried = _tried_describe_tables(observations)
    for candidate in targets:
        if candidate not in tried:
            return candidate
    return ""


def _tool_done(
    tool: str,
    observations: list[dict],
    *,
    default_tables: list[str],
    plan: dict[str, Any] | None = None,
) -> bool:
    if tool == "describe_table":
        return _describe_table_done(default_tables, observations, plan=plan)
    if tool == "list_relations":
        if _tried_list_relation_tables(observations):
            return True
        # 兼容无 table 参数的历史观察
        return any(o.get("tool") == tool for o in observations)
    if tool == "get_join_path":
        if _tried_join_pairs(observations):
            return True
        return any(o.get("tool") == tool for o in observations)
    if tool in _SEARCH_TOOLS or tool == "run_probe_sql":
        return any(o.get("tool") == tool for o in observations)
    return any(o.get("tool") == tool for o in observations)


def _needs_tools_complete(
    plan: dict[str, Any] | None,
    observations: list[dict],
    *,
    default_tables: list[str],
) -> bool:
    """plan.needs_tool 清单是否全部完成（空清单不强制结束）。"""
    needs = _plan_needs_tools(plan)
    if not needs:
        return False
    return all(
        _tool_done(tool, observations, default_tables=default_tables, plan=plan) for tool in needs
    )


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
            if _tool_done(tool, observations, default_tables=default_tables, plan=plan):
                continue
            args = _default_tool_args(
                tool,
                default_tables,
                question,
                observations,
                plan=plan,
            )
            if is_duplicate_tool_call(tool, args, observations):
                continue
            return {
                "action": "tool",
                "tool": tool,
                "args": args,
            }
    return {"action": "finish"}


def _default_tool_args(
    tool: str,
    tables: list[str],
    question: str,
    observations: list[dict] | None = None,
    *,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observations = observations or []
    if tool == "describe_table":
        table = _next_describe_table(tables, observations, plan=plan)
        if table:
            return {"table": table}
    if tool == "list_relations":
        table = _next_list_relations_table(tables, observations)
        if table:
            return {"table": table}
    if tool == "get_join_path":
        join_args = _next_join_path_args(tables, observations)
        if join_args:
            return join_args
    candidates = _pick_candidate_tables(tables, limit=5)
    if tool == "list_relations" and candidates:
        return {"table": candidates[0]}
    if tool == "get_join_path" and len(candidates) >= 2:
        return {"from_table": candidates[0], "to_table": candidates[1]}
    if tool in _SEARCH_TOOLS:
        return {"query": question}
    return {}


def _sanitize_tool_args(
    tool: str,
    args: dict[str, Any],
    *,
    default_tables: list[str],
    observations: list[dict],
    question: str,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool == "describe_table":
        table = str(args.get("table") or "")
        norm = _normalize_meta_table_name(table)
        tried = _tried_describe_tables(observations)
        candidates = _pick_candidate_tables(default_tables, limit=5)
        targets = _plan_describe_targets(plan, default_tables)
        allowed = set(targets) | set(candidates)
        if norm and norm in allowed and norm not in tried:
            return {"table": norm}
        return _default_tool_args(tool, default_tables, question, observations, plan=plan)

    if tool == "list_relations":
        table = _normalize_meta_table_name(str(args.get("table") or ""))
        tried = _tried_list_relation_tables(observations)
        candidates = set(_pick_candidate_tables(default_tables, limit=5))
        if table and table in candidates and table not in tried:
            return {"table": table}
        return _default_tool_args(tool, default_tables, question, observations, plan=plan)

    if tool == "get_join_path":
        a = _normalize_meta_table_name(str(args.get("from_table") or ""))
        b = _normalize_meta_table_name(str(args.get("to_table") or ""))
        candidates = set(_pick_candidate_tables(default_tables, limit=5))
        if a and b and a in candidates and b in candidates:
            if tuple(sorted((a, b))) not in _tried_join_pairs(observations):
                return {"from_table": a, "to_table": b}
        return _default_tool_args(tool, default_tables, question, observations, plan=plan)

    return args


def _avoid_duplicate_action(
    action: dict[str, Any],
    *,
    observations: list[dict],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """若拟定 tool 调用与历史指纹重复，则改走 fallback 或 finish。"""
    if action.get("action") != "tool":
        return action
    tool = str(action.get("tool") or "")
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    if not is_duplicate_tool_call(tool, args, observations):
        return action
    if fallback.get("action") == "tool":
        fb_tool = str(fallback.get("tool") or "")
        fb_args = fallback.get("args") if isinstance(fallback.get("args"), dict) else {}
        if not is_duplicate_tool_call(fb_tool, fb_args, observations):
            return fallback
    return {"action": "finish"}


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
    # plan.needs_tool 全部完成后直接结束，禁止继续自由探索
    if _needs_tools_complete(plan, observations, default_tables=default_tables):
        return {"action": "finish"}

    fallback = _fallback_action(plan, observations, default_tables=default_tables, question=question)
    plan_text = json.dumps(plan or {}, ensure_ascii=False)[:2000]
    obs_text = _format_observations(observations)
    needs = _plan_needs_tools(plan)
    needs_hint = (
        f"当前 plan.needs_tool={needs}；清单内工具全部完成后必须 {{\"action\":\"finish\"}}，"
        "禁止再调用清单外工具。"
        if needs
        else ""
    )
    system = (
        build_agent_system_preamble()
        + "你是企业问数 Agent，根据问句、规划与已有观察，选择下一步只读工具。"
        f"可用工具：{', '.join(_AGENT_TOOLS)}。"
        "输出 JSON：{\"action\":\"tool\",\"tool\":\"describe_table\",\"args\":{\"table\":\"表名\"}}"
        "或 {\"action\":\"finish\"} 表示信息足够可生成 SQL。"
        "或 {\"action\":\"ask_user\",\"tool\":\"ask_user_question\",\"args\":{\"reason\":\"...\",\"questions\":[...]}}"
        "当指标/实体仍歧义且无法安全出 SQL 时用 ask_user，禁止瞎猜 finish。"
        "硬性禁止重复：同一 fingerprint 的工具调用只允许一次"
        "（同表 describe_table / list_relations、同端点 get_join_path、同 query 的 search_*、同 SQL 的 run_probe_sql）；"
        "已出现在【禁止重复调用】中的指纹不得再选。"
        f"{needs_hint}"
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
            return _avoid_duplicate_action(fallback, observations=observations, fallback={"action": "finish"})
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
            return _avoid_duplicate_action(fallback, observations=observations, fallback={"action": "finish"})
        # 有 needs_tool 时，禁止清单外探索（澄清除外）
        if needs and tool not in needs:
            return _avoid_duplicate_action(fallback, observations=observations, fallback={"action": "finish"})
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        if not args:
            args = _default_tool_args(tool, default_tables, question, observations, plan=plan)
        else:
            args = _sanitize_tool_args(
                tool,
                args,
                default_tables=default_tables,
                observations=observations,
                question=question,
                plan=plan,
            )
        if tool == "describe_table":
            table = _normalize_meta_table_name(str((args or {}).get("table") or ""))
            if not table:
                return _avoid_duplicate_action(fallback, observations=observations, fallback={"action": "finish"})
            if table in _tried_describe_tables(observations):
                nxt = _next_describe_table(default_tables, observations, plan=plan)
                if nxt:
                    args = {"table": nxt}
                else:
                    return _avoid_duplicate_action(fallback, observations=observations, fallback={"action": "finish"})
        chosen = {"action": "tool", "tool": tool, "args": args}
        return _avoid_duplicate_action(chosen, observations=observations, fallback=fallback)
    except Exception:
        return _avoid_duplicate_action(fallback, observations=observations, fallback={"action": "finish"})


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
