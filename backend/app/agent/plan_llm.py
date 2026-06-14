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


def _normalize_filter_hint(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    hint: dict[str, Any] = {}
    if raw.get("activity_id") is not None:
        try:
            hint["activity_id"] = int(raw["activity_id"])
        except (TypeError, ValueError):
            pass
    if raw.get("activity_name"):
        hint["activity_name"] = str(raw["activity_name"]).strip()
    projects = raw.get("project_names") or raw.get("projects")
    if isinstance(projects, list):
        hint["project_names"] = [str(p).strip() for p in projects if str(p).strip()]
    return hint


def _normalize_metrics(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(m).strip() for m in raw if str(m).strip()]


def _normalize_plan(raw: dict[str, Any]) -> dict[str, Any]:
    """校验并补齐 plan 字段。"""
    complexity = str(raw.get("complexity") or "high").lower()
    if complexity not in ("low", "medium", "high"):
        complexity = "high"
    intent = str(raw.get("intent") or "open_query")
    multi_sql = bool(raw.get("multi_sql"))
    assembly_mode = raw.get("assembly_mode")
    if assembly_mode is not None:
        assembly_mode = str(assembly_mode).strip() or None
    join_key = raw.get("join_key")
    if join_key is not None:
        join_key = str(join_key).strip() or None

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
        sql_step = bool(step.get("sql_step"))
        entity_label = step.get("entity_label")
        if entity_label is not None:
            entity_label = str(entity_label).strip() or None
        normalized_steps.append(
            {
                "id": step.get("id") or idx,
                "goal": str(step.get("goal") or "").strip() or f"步骤 {idx}",
                "tables": step.get("tables") if isinstance(step.get("tables"), list) else [],
                "needs_tool": [str(t) for t in needs if t],
                "aggregation": step.get("aggregation"),
                "pivot_hint": step.get("pivot_hint"),
                "sql_step": sql_step,
                "entity_label": entity_label,
                "join_key": step.get("join_key") or join_key,
                "filter_hint": _normalize_filter_hint(step.get("filter_hint")),
                "metrics": _normalize_metrics(step.get("metrics")),
            }
        )

    if multi_sql:
        sql_step_count = sum(1 for s in normalized_steps if s.get("sql_step"))
        if sql_step_count < 2 and len(normalized_steps) >= 2:
            for s in normalized_steps:
                s["sql_step"] = True
        elif sql_step_count < 2 and len(normalized_steps) == 1:
            normalized_steps[0]["sql_step"] = True

    sources = raw.get("sources") or ["meta:recall"]
    if not isinstance(sources, list):
        sources = ["meta:recall"]

    plan: dict[str, Any] = {
        "complexity": complexity,
        "intent": intent,
        "multi_sql": multi_sql,
        "steps": normalized_steps,
        "sources": [str(s) for s in sources],
        "metrics": _normalize_metrics(raw.get("metrics")),
    }
    if assembly_mode:
        plan["assembly_mode"] = assembly_mode
    if join_key:
        plan["join_key"] = join_key
    return plan


async def generate_plan_from_llm(
    *,
    settings: Settings,
    question: str,
    recall_summary: str,
    l1_score: int | None = None,
    l1_sql_preview: str | None = None,
) -> dict[str, Any] | None:
    """
    调用 LLM 生成问句分解 plan。

    Returns:
        规范化后的 plan dict；解析失败返回 None。
    """
    llm = build_llm(settings)
    system = (
        "你是企业问数系统的查询规划助手。根据用户问句与种子召回，输出 JSON 计划（仅 JSON）。\n"
        "字段说明：\n"
        "- complexity: low | medium | high\n"
        "- intent: 如 simple_aggregate | multi_dim_report | entity_compare | open_query\n"
        "- multi_sql: boolean，是否必须「分步执行多条独立 SQL，再由程序组装结果」\n"
        "  · true：多个实体各自一条 SQL（禁止单条 SQL 用 IN 查多个活动再 GROUP BY），"
        "每步 sql_step=true，assembly_mode 填 join_by_date 或 pivot\n"
        "  · false：一条 SQL 即可（可用 WITH/CTE），走常规生成\n"
        "- assembly_mode: multi_sql=true 时填 join_by_date | pivot | join\n"
        "- join_key: 组装对齐键，中文别名如「日期」\n"
        "- metrics: 问句要求的全部指标/输出列（中文），如打卡人数、跳绳运动个数、跑步运动个数\n"
        "- steps: 每步含 id, goal, needs_tool, sql_step, entity_label, filter_hint, metrics\n"
        "  · sql_step=true 表示该步单独生成并执行一条 SELECT\n"
        "  · goal 须写清本步要输出的全部指标（不可只写「按日指标」而遗漏问句中的分项）\n"
        "  · metrics 为本步 SQL 结果列应覆盖的指标（与问句一致，逐步可相同）\n"
        "  · filter_hint 可含 activity_id、activity_name、project_names（项目名列表）\n"
        "  · 问句若要求按运动项目分项统计，needs_tool 应含 list_relations/get_join_path，"
        "并在 goal 中写明需关联项目表（如 sport_project）或按 project 过滤\n"
        "  · needs_tool 从 describe_table, list_relations, get_join_path, search_metrics, "
        "search_field_values, search_sql_examples 选取\n"
        "判定原则（由你根据语义判断，勿依赖固定关键词表）：\n"
        "· 简单单指标、单表、单时间范围 → complexity=low, multi_sql=false, 1 步\n"
        "· 多实体对比且需按日对齐宽表 → multi_sql=true，每实体一步 sql_step\n"
        "· 问句含多个指标（如打卡人数 + 多个项目运动个数）→ metrics 与每步 goal 须全部列出，"
        "SQL 阶段需 JOIN/过滤项目维度，禁止仅用 SUM(sport_value) 一个总数代替分项\n"
        "· 复杂多维但一条 SQL 可完成 → multi_sql=false, complexity=high, needs_tool 探索\n"
    )
    user_parts = [
        f"用户问句：{question}",
        "",
        f"种子召回摘要：\n{recall_summary}",
    ]
    if l1_score is not None and l1_score > 0:
        user_parts.append(f"\nL1 样例软参考得分：{l1_score}（仅供参考，仍以问句语义决定是否分步 SQL）")
    if l1_sql_preview:
        preview = l1_sql_preview.strip()
        if len(preview) > 800:
            preview = preview[:800] + "..."
        user_parts.append(f"\nL1 参考 SQL（勿照搬；若 multi_sql=true 应拆成多条）：\n{preview}")
    user_parts.extend(
        [
            "",
            "请输出 JSON 示例：",
            '{"complexity":"high","intent":"entity_compare","multi_sql":true,'
            '"assembly_mode":"join_by_date","join_key":"日期",'
            '"metrics":["打卡人数","跳绳运动个数","跑步运动个数"],'
            '"steps":[{"id":1,"goal":"活动5780按日：打卡人数、跳绳与跑步项目运动个数",'
            '"sql_step":true,"entity_label":"活动5780",'
            '"metrics":["打卡人数","跳绳运动个数","跑步运动个数"],'
            '"filter_hint":{"activity_id":5780,"project_names":["跳绳","跑步"]},'
            '"needs_tool":["describe_table","list_relations"]}],'
            '"sources":["meta:recall"]}',
        ]
    )
    user = "\n".join(user_parts)
    try:
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed = _extract_json(content)
        if parsed:
            return _normalize_plan(parsed)
    except Exception:
        return None
    return None
