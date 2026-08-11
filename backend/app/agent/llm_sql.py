"""
LLM 生成 SQL：OpenAI 兼容 API（本机 Ollama 等）。
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.llm_client import thinking_request_body
from app.policy.role_policy import LLM_JOIN_ALIAS_SYSTEM_HINT
from app.security.prompt_boundary import build_sql_system_preamble, wrap_untrusted
from app.system.runtime_config import resolve_chat_llm
from config.settings import Settings

_SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*([\s\S]*?)```", re.IGNORECASE)
_SQL_START_RE = re.compile(r"((?:WITH|SELECT)[\s\S]+)", re.IGNORECASE)

_CONTEXT_ONLY_HINT = (
    "严格遵守上下文【允许查询的业务表】与【候选表字段清单】中的真实表名与列名，禁止编造。"
    "时间/日期筛选须使用清单中的日期或时间列，禁止把中文「日期」当作列名。"
)

# 业务库普遍不支持中文 AS；展示层再 localize_result_columns 转中文表头。
_ENGLISH_ALIAS_HINT = (
    "SELECT 输出列别名必须使用英文标识符（snake_case 或 metric_code），"
    "禁止中文别名、禁止用引号包裹中文 AS；中文表头由系统在展示/导出时转换。"
)


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
    """构造 ChatOpenAI 客户端（经 Catalog adapterKey，默认 openai_compatible）。"""
    from app.system.llm_adapters import get_adapter

    cfg = resolve_chat_llm(settings)
    adapter = get_adapter(provider_code=cfg.provider)
    kwargs: dict = adapter.chat_kwargs(cfg)
    extra = thinking_request_body(settings, cfg)
    if extra:
        kwargs["extra_body"] = extra
    return ChatOpenAI(**kwargs)


def _subquery_per_branch_hint() -> str:
    from app.system.sql_context import resolve_sql_context

    ctx = resolve_sql_context()
    return (
        "【分路聚合硬性约束】问句涉及多个来源表，彼此无表关系、仅经同一汇聚表关联："
        f"{ctx.aggregate_strategy_hint()}"
        "禁止照搬上一轮会话 SQL 中的多表 JOIN 写法。"
        "人数类指标仍可用 COUNT(DISTINCT ...) 放在子查询内。"
    )


async def generate_sql_from_llm(
    *,
    settings: Settings,
    question: str,
    context_text: str,
    compact: bool = False,
    correction_hint: str | None = None,
    previous_sql: str | None = None,
    plan: dict | None = None,
    thinking_queue: Any | None = None,
) -> tuple[str | None, int | None, int | None]:
    """
    调用 LLM 生成 SQL。

    Returns:
        (sql, token_in, token_out)；失败时 sql 为 None。
    """
    from app.system.sql_context import resolve_sql_context

    sql_ctx = resolve_sql_context(settings)
    system = (
        build_sql_system_preamble()
        + "你是企业问数系统的 SQL 生成助手，只为业务库生成只读查询。"
        + f"目标方言：{sql_ctx.prompt_dialect_label}。"
        + _CONTEXT_ONLY_HINT
        + _ENGLISH_ALIAS_HINT
        + LLM_JOIN_ALIAS_SYSTEM_HINT
    )
    if (plan or {}).get("aggregate_strategy") == "subquery_per_branch":
        system += _subquery_per_branch_hint()
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

    from app.agent.llm_client import complete_messages

    content, _reasoning, token_in, token_out = await complete_messages(
        settings,
        messages,
        thinking_queue=thinking_queue,
    )
    sql = _extract_sql(content)

    return sql, token_in, token_out


async def generate_sql_step_from_llm(
    *,
    settings: Settings,
    question: str,
    context_text: str,
    plan_steps: list[dict],
    plan: dict | None = None,
    thinking_queue: Any | None = None,
) -> tuple[str | None, list[dict], int | None, int | None]:
    """
    按 plan 步骤生成分步 CTE SQL（§11.7.4 · 第 8 周）。

    Returns:
        (完整 SQL, sql_steps 元数据, token_in, token_out)
    """
    steps_text = "\n".join(
        f"  步骤 {s.get('id')}: {s.get('goal')}"
        + (f"（{s.get('aggregation')}）" if s.get("aggregation") else "")
        + (f" pivot={s.get('pivot_hint')}" if s.get("pivot_hint") else "")
        for s in plan_steps
    )
    from app.system.sql_context import resolve_sql_context

    sql_ctx = resolve_sql_context(settings)
    system = (
        "你是企业问数 SQL 生成助手。根据规划步骤与用户问题生成一条可执行的只读 SELECT。"
        f"目标方言：{sql_ctx.prompt_dialect_label}。"
        "优先写简单 SQL：单条 SELECT + WHERE/GROUP BY 即可。"
        "禁止无关 CROSS JOIN、笛卡尔积或过度嵌套；多维度对比用 GROUP BY 或条件聚合。"
        "趋势类问题按上下文中的日期/时间列 GROUP BY；"
        "人数类指标用 COUNT(DISTINCT 清单中的人员标识列) 或 COUNT(*) 视字段含义而定。"
        + _CONTEXT_ONLY_HINT
        + _ENGLISH_ALIAS_HINT
        + LLM_JOIN_ALIAS_SYSTEM_HINT
    )
    if (plan or {}).get("aggregate_strategy") == "subquery_per_branch":
        system += _subquery_per_branch_hint()
    user = (
        f"{context_text}\n\n"
        f"规划步骤：\n{steps_text}\n\n"
        f"用户问题：{question}\n\n"
        "请直接输出一条完整 SQL（单条 SELECT，必要时用标量子查询分路聚合），"
        "列别名须为英文标识符。"
    )
    from app.agent.llm_client import complete_messages

    content, _reasoning, token_in, token_out = await complete_messages(
        settings,
        [SystemMessage(content=system), HumanMessage(content=user)],
        thinking_queue=thinking_queue,
    )
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

    return sql, sql_steps_meta, token_in, token_out


async def generate_sql_for_plan_step(
    *,
    settings: Settings,
    question: str,
    context_text: str,
    step: dict,
    prior_results_summary: str,
    thinking_queue: Any | None = None,
) -> tuple[str | None, int | None, int | None]:
    """
    为 plan 中单一步骤生成独立 SELECT（分步执行路径）。

    Returns:
        (sql, token_in, token_out)
    """
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
            f"必须且只能查询 activity_id = {filter_hint['activity_id']} 的实体数据；"
            "禁止 WHERE activity_id IN (...) 一次查多个实体（activity_id 须为上下文候选字段）。"
        )
    if filter_hint.get("activity_name"):
        name = str(filter_hint["activity_name"])
        short = name[:60] + ("…" if len(name) > 60 else "")
        constraints.append(
            f"必须且只能查询名称与「{short}」匹配的那一个实体；禁止一次查多个。"
        )
    project_names = filter_hint.get("project_names") or []
    if project_names:
        projects = "、".join(project_names[:8])
        constraints.append(
            f"问句要求按项目/维度分项：{projects}。"
            "须通过上下文中的关联表与项目名字段（或字段取值映射）过滤/分组，"
            "为每个分项在结果中提供独立指标列；"
            "禁止用一个未分项的总聚合列代替多个分项。"
        )
    if step_metrics:
        metrics_line = "、".join(step_metrics[:12])
        constraints.append(
            f"本步结果须覆盖以下业务指标（语义为中文，SQL 别名须英文）：{metrics_line}。"
            "人数类用 COUNT(DISTINCT 人员标识列)；各分项分别聚合，别名用 snake_case。"
        )
    constraint_text = "\n".join(constraints)

    from app.system.sql_context import resolve_sql_context

    sql_ctx = resolve_sql_context(settings)
    system = (
        "你是企业问数 SQL 生成助手。根据用户问句、规划步骤与上下文，生成一条可独立执行的只读 SELECT。"
        f"目标方言：{sql_ctx.prompt_dialect_label}。"
        "本步骤 SQL 将单独执行；多实体对比时每一步只查一个实体，由程序按对齐键合并结果。"
        "须完整实现问句与本步 goal/metrics 中的全部指标，不得省略维度或合并为单一总数。"
        "多表关联时使用上下文【候选表字段】中的外键与维度表；"
        "结果须含英文对齐键列（如 date / stat_date）及各指标英文别名列；"
        "优先 JOIN + GROUP BY 或条件聚合。"
        + _CONTEXT_ONLY_HINT
        + _ENGLISH_ALIAS_HINT
        + LLM_JOIN_ALIAS_SYSTEM_HINT
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
        user_parts.append(f"本步 metrics（业务语义）：{'、'.join(step_metrics)}")
    if constraint_text:
        user_parts.extend(["", "【本步硬性约束】", constraint_text])
    user_parts.extend(
        ["", "请输出本步骤的一条 SELECT（英文列别名，须含对齐键列如 date/stat_date）。"]
    )
    user = "\n".join(user_parts)
    from app.agent.llm_client import complete_messages

    content, _reasoning, token_in, token_out = await complete_messages(
        settings,
        [SystemMessage(content=system), HumanMessage(content=user)],
        thinking_queue=thinking_queue,
    )
    sql = _extract_sql(content)
    return sql, token_in, token_out
