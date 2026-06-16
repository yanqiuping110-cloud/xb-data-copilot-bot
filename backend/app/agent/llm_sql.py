"""
LLM 生成 SQL：OpenAI 兼容 API（本机 Ollama 等）。
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.policy.role_policy import LLM_JOIN_ALIAS_SYSTEM_HINT
from app.security.prompt_boundary import build_sql_system_preamble, wrap_untrusted
from config.settings import Settings

_SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*([\s\S]*?)```", re.IGNORECASE)
_SQL_START_RE = re.compile(r"((?:WITH|SELECT)[\s\S]+)", re.IGNORECASE)


def _extract_sql(text: str) -> str | None:
    """从模型输出中提取 SELECT 或 WITH ... SELECT 语句。"""
    stripped = text.strip()
    block = _SQL_BLOCK_RE.search(stripped)
    candidate = block.group(1).strip() if block else stripped
    upper = candidate.upper()
    if upper.startswith("SELECT") or upper.startswith("WITH"):
        return candidate.rstrip(";").strip()
    match = _SQL_START_RE.search(candidate)
    if match:
        return match.group(1).rstrip(";").strip()
    return None


def build_llm(settings: Settings) -> ChatOpenAI:
    """构造 ChatOpenAI 客户端（兼容 Ollama / 通义等）。"""
    return ChatOpenAI(
        base_url=settings.llm_api_base,
        api_key=settings.llm_api_key or "ollama",
        model=settings.llm_model,
        temperature=0,
        timeout=settings.llm_timeout_sec,
    )


async def generate_sql_from_llm(
    *,
    settings: Settings,
    question: str,
    context_text: str,
    compact: bool = False,
    correction_hint: str | None = None,
    previous_sql: str | None = None,
) -> tuple[str | None, int | None, int | None]:
    """
    调用 LLM 生成 SQL。

    Returns:
        (sql, token_in, token_out)；失败时 sql 为 None。
    """
    llm = build_llm(settings)
    system = (
        build_sql_system_preamble()
        + "你是企业问数系统的 SQL 生成助手，只为业务库生成只读查询。"
        "严格遵守上下文中的表白名单与 MySQL 5.7 语法。"
        "只能使用上下文中【候选表字段清单】列出的真实列名，禁止编造任何字段。"
        "时间/日期筛选请用 create_time、activity_start_time 等真实列，禁止把中文「日期」当作列名。"
        "SELECT 列别名优先使用中文（如 AS 学生名、AS 入学年份）；"
        "仅当用户明确要求英文表头时才使用英文别名。"
        f"{LLM_JOIN_ALIAS_SYSTEM_HINT}"
    )
    bounded_q = wrap_untrusted(
        "user_question",
        question,
        max_chars=2000,
        enabled=settings.prompt_boundary_enabled,
    )
    user_parts = [context_text, "", f"用户问题：{bounded_q}"]
    if correction_hint and previous_sql:
        user_parts.extend(
            [
                "",
                f"上次生成的 SQL 未通过校验：{correction_hint}",
                f"上次 SQL：{previous_sql}",
                "请根据错误信息修正后重新生成 SELECT。",
            ]
        )
    user_parts.extend(["", "请生成一条 SELECT 语句："])
    if compact:
        user_parts.insert(0, "（精简模式：仅输出 SQL，不要注释）")
    messages = [SystemMessage(content=system), HumanMessage(content="\n".join(user_parts))]

    response = await llm.ainvoke(messages)
    content = response.content if isinstance(response.content, str) else str(response.content)
    sql = _extract_sql(content)

    token_in = token_out = None
    meta = getattr(response, "response_metadata", None) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    if usage:
        token_in = usage.get("prompt_tokens") or usage.get("input_tokens")
        token_out = usage.get("completion_tokens") or usage.get("output_tokens")

    return sql, token_in, token_out


async def generate_sql_step_from_llm(
    *,
    settings: Settings,
    question: str,
    context_text: str,
    plan_steps: list[dict],
) -> tuple[str | None, list[dict], int | None, int | None]:
    """
    按 plan 步骤生成分步 CTE SQL（§11.7.4 · 第 8 周）。

    Returns:
        (完整 SQL, sql_steps 元数据, token_in, token_out)
    """
    llm = build_llm(settings)
    steps_text = "\n".join(
        f"  步骤 {s.get('id')}: {s.get('goal')}"
        + (f"（{s.get('aggregation')}）" if s.get("aggregation") else "")
        + (f" pivot={s.get('pivot_hint')}" if s.get("pivot_hint") else "")
        for s in plan_steps
    )
    system = (
        "你是企业问数 SQL 生成助手。根据规划步骤与用户问题生成一条可执行的 MySQL 只读 SELECT。"
        "优先写简单 SQL：单条 SELECT + WHERE/GROUP BY 即可；仅在步骤明确需要时才使用 WITH CTE。"
        "禁止无关 CROSS JOIN、笛卡尔积或过度嵌套；对比多个项目用 GROUP BY 或条件聚合。"
        "趋势类问题按日期 GROUP BY；人数/人次用 COUNT(DISTINCT user_id) 或 COUNT(*) 视上下文而定。"
        "严格遵守上下文表白名单与真实列名，禁止编造字段。"
        f"{LLM_JOIN_ALIAS_SYSTEM_HINT}"
    )
    user = (
        f"{context_text}\n\n"
        f"规划步骤：\n{steps_text}\n\n"
        f"用户问题：{question}\n\n"
        "请直接输出一条完整 SQL（可用 WITH 或单条 SELECT），列别名优先中文。"
    )
    response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = response.content if isinstance(response.content, str) else str(response.content)
    sql = _extract_sql(content)

    sql_steps_meta = [
        {
            "step_id": s.get("id"),
            "goal": s.get("goal"),
            "aggregation": s.get("aggregation"),
            "pivot_hint": s.get("pivot_hint"),
        }
        for s in plan_steps
    ]

    token_in = token_out = None
    meta = getattr(response, "response_metadata", None) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    if usage:
        token_in = usage.get("prompt_tokens") or usage.get("input_tokens")
        token_out = usage.get("completion_tokens") or usage.get("output_tokens")

    return sql, sql_steps_meta, token_in, token_out


async def generate_sql_for_plan_step(
    *,
    settings: Settings,
    question: str,
    context_text: str,
    step: dict,
    prior_results_summary: str,
) -> tuple[str | None, int | None, int | None]:
    """
    为 plan 中单一步骤生成独立 SELECT（分步执行路径）。

    Returns:
        (sql, token_in, token_out)
    """
    llm = build_llm(settings)
    step_id = step.get("id")
    goal = step.get("goal") or ""
    agg = step.get("aggregation") or ""
    pivot = step.get("pivot_hint") or ""
    step_line = f"步骤 {step_id}: {goal}"
    if agg:
        step_line += f"（{agg}）"
    if pivot:
        step_line += f" pivot={pivot}"

    filter_hint = step.get("filter_hint") or {}
    step_metrics = step.get("metrics") or []
    constraints: list[str] = []
    if filter_hint.get("activity_id") is not None:
        constraints.append(
            f"必须且只能查询 activity_id = {filter_hint['activity_id']} 的活动数据；"
            "禁止 WHERE activity_id IN (...) 同时查多个活动。"
        )
    if filter_hint.get("activity_name"):
        name = str(filter_hint["activity_name"])
        short = name[:60] + ("…" if len(name) > 60 else "")
        constraints.append(
            f"必须且只能查询活动名称与「{short}」匹配的那一个活动；禁止一次查多个活动。"
        )
    project_names = filter_hint.get("project_names") or []
    if project_names:
        projects = "、".join(project_names[:8])
        constraints.append(
            f"问句要求按运动项目分项：{projects}。"
            "须通过 project_id JOIN sport_project（或上下文中的项目表）按项目过滤/分组，"
            "为每个项目在结果中提供独立指标列（如跳绳运动个数、跑步运动个数）；"
            "禁止仅用 SUM(sport_value) 一个总数列代替多个项目分项。"
        )
    if step_metrics:
        metrics_line = "、".join(step_metrics[:12])
        constraints.append(
            f"本步结果列须覆盖以下指标（中文列名）：{metrics_line}。"
            "打卡人数用 COUNT(DISTINCT 人员标识列)；各项目运动个数分别聚合。"
        )
    constraint_text = "\n".join(constraints)

    system = (
        "你是企业问数 SQL 生成助手。根据用户问句、规划步骤与上下文，生成一条可独立执行的 MySQL 只读 SELECT。"
        "本步骤 SQL 将单独执行；多活动对比时每一步只查一个活动，由程序按日期合并结果。"
        "须完整实现问句与本步 goal/metrics 中的全部指标，不得省略项目维度或合并为单一运动总数。"
        "事实表常见 sport_activity_qzs_time（含 activity_id、project_id、sport_value、record_date）；"
        "项目维度常见 sport_project，通过 project_id 关联。"
        "结果须含日期列（别名「日期」）及各指标列；优先 JOIN + GROUP BY 或条件聚合。"
        "严格遵守上下文表白名单与真实列名，禁止编造字段。"
        f"{LLM_JOIN_ALIAS_SYSTEM_HINT}"
    )
    user_parts = [
        context_text,
        "",
        prior_results_summary,
        "",
        f"用户问题：{question}",
        "",
        f"当前仅需完成：{step_line}",
    ]
    if step_metrics:
        user_parts.append(f"本步 metrics：{'、'.join(step_metrics)}")
    if constraint_text:
        user_parts.extend(["", "【本步硬性约束】", constraint_text])
    user_parts.extend(["", "请输出本步骤的一条 SELECT（列别名优先中文，须含日期列）。"])
    user = "\n".join(user_parts)
    response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = response.content if isinstance(response.content, str) else str(response.content)
    sql = _extract_sql(content)

    token_in = token_out = None
    meta = getattr(response, "response_metadata", None) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    if usage:
        token_in = usage.get("prompt_tokens") or usage.get("input_tokens")
        token_out = usage.get("completion_tokens") or usage.get("output_tokens")
    return sql, token_in, token_out
