"""
问句规划 LLM：输出 JSON plan（§11.7.3）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.chart_builder import normalize_visualization_intent
from app.agent.llm_client import complete_messages
from app.ask.l1_service import L1ExampleCandidate
from config.settings import Settings

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

# 与 build_llm_context 一致的全量上下文上限（字符），超出截断并注明
_PLAN_CONTEXT_MAX_CHARS = 20_000


def _truncate_plan_context(context_text: str, *, max_chars: int = _PLAN_CONTEXT_MAX_CHARS) -> str:
    text = (context_text or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n…（上下文已截断，原长 {len(text)} 字符）"


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
    vis_raw = raw.get("visualization")
    if vis_raw is not None:
        plan["visualization"] = normalize_visualization_intent(vis_raw)
    return plan


async def generate_plan_from_llm(
    *,
    settings: Settings,
    question: str,
    recall_summary: str,
    context_text: str = "",
    selected_l1_examples: list[L1ExampleCandidate] | None = None,
    thinking_queue: Any | None = None,
) -> dict[str, Any] | None:
    """
    调用 LLM 生成问句分解 plan。

    context_text 为 build_llm_context 产出的完整问数上下文（字段/JOIN/指标口径等），
    与 SQL 生成阶段一致，供 Plan 判定 multi_sql 与步骤分解。

    Returns:
        规范化后的 plan dict；解析失败返回 None。
    """
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
        "- metrics: 问句要求的全部指标/输出列（中文），如参与人数、各项目运动个数\n"
        "- steps: 每步含 id, goal, needs_tool, sql_step, entity_label, filter_hint, metrics\n"
        "  · sql_step=true 表示该步单独生成并执行一条 SELECT\n"
        "  · goal 须写清本步要输出的全部指标（不可只写「按日指标」而遗漏问句中的分项）\n"
        "  · metrics 为本步 SQL 结果列应覆盖的指标（与问句一致，逐步可相同）\n"
        "  · filter_hint 可含 activity_id、activity_name、project_names（问句中的项目/维度名列表）\n"
        "  · 问句若要求按项目/维度分项统计，needs_tool 应含 list_relations/get_join_path，"
        "并在 goal 中写明需关联维度表或按项目字段过滤\n"
        "  · needs_tool 从 describe_table, list_relations, get_join_path, search_metrics, "
        "search_field_values, search_sql_examples 选取\n"
        "判定原则（由你根据语义判断，勿依赖固定关键词表）：\n"
        "· 简单单指标、单表、单时间范围 → complexity=low, multi_sql=false, 1 步\n"
        "· 多实体对比且需按日对齐宽表 → multi_sql=true，每实体一步 sql_step\n"
        "· 问句含多个指标或多个分项 → metrics 与每步 goal 须全部列出，"
        "SQL 阶段需 JOIN/过滤维度，禁止用一个未分项的总聚合代替分项\n"
        "· 复杂多维但一条 SQL 可完成 → multi_sql=false, complexity=high, needs_tool 探索\n"
        "- visualization: 图表展示意图（必填）\n"
        "  · enabled: boolean，是否尝试生成图表（明细/列表/单值汇总 → false）\n"
        "  · user_explicit: boolean，用户是否明确要求图表/趋势/占比\n"
        "  · preferred_types: 数组，从 line|bar|column|pie|area|scatter|combo|none 选，按优先级\n"
        "  · reason: 中文简述判定依据\n"
        "  · fallback_to_table: true（不可图表时仍返回表格）\n"
        "  · 趋势/每日/按月 → enabled=true, preferred_types=[line,area]\n"
        "  · 对比/排名/各项目 → preferred_types=[bar,column]\n"
        "  · 占比/构成 → preferred_types=[pie,bar]\n"
        "  · 明细/列表 → enabled=false\n"
    )
    user_parts = [
        f"用户问句：{question}",
        "",
        f"种子召回摘要：\n{recall_summary}",
    ]
    full_context = _truncate_plan_context(context_text)
    if full_context:
        user_parts.extend(
            [
                "",
                "问数上下文（与 SQL 生成一致；含表白名单、字段清单、JOIN、指标口径、过滤与约束）：",
                full_context,
            ]
        )
    if selected_l1_examples:
        user_parts.append("\n【已精选 L1 样例（软参考；勿照搬；multi_sql=true 时应拆成多条）】")
        for ex in selected_l1_examples:
            user_parts.append(f"- id={ex.id} 问法：{ex.question_pattern}")
            if ex.description:
                user_parts.append(f"  说明：{ex.description[:300]}")
            if ex.select_reason:
                user_parts.append(f"  选用理由：{ex.select_reason[:200]}")
            preview = ex.sql_text.strip()
            if len(preview) > 800:
                preview = preview[:800] + "..."
            user_parts.append(f"  SQL：{preview}")
    user_parts.extend(
        [
            "",
            "请输出 JSON 示例：",
            '{"complexity":"high","intent":"entity_compare","multi_sql":true,'
            '"assembly_mode":"join_by_date","join_key":"日期",'
            '"metrics":["指标A","指标B","指标C"],'
            '"steps":[{"id":1,"goal":"实体X按日：指标A、B、C",'
            '"sql_step":true,"entity_label":"实体X",'
            '"metrics":["指标A","指标B","指标C"],'
            '"filter_hint":{"activity_id":1001,"project_names":["项目甲","项目乙"]},'
            '"needs_tool":["describe_table","list_relations"]}],'
            '"visualization":{"enabled":true,"user_explicit":false,'
            '"preferred_types":["line","bar"],"reason":"多实体按日对比",'
            '"fallback_to_table":true},'
            '"sources":["meta:recall"]}',
        ]
    )
    user = "\n".join(user_parts)
    try:
        content, _reasoning, _ti, _to = await complete_messages(
            settings,
            [SystemMessage(content=system), HumanMessage(content=user)],
            thinking_queue=thinking_queue,
        )
        parsed = _extract_json(content)
        if parsed:
            return _normalize_plan(parsed)
    except Exception:
        return None
    return None
