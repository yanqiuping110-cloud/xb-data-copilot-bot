"""
语义验证节点 verify_answer（§11.7.4 · 第 9 周）。

执行 SQL 后轻量判断：结果是否为空、问句维度/指标是否在结果列中体现。
失败时带 sample_rows 触发 correct_sql 或（Agent 路径）追加观察后重试。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.llm_sql import build_llm
from app.agent.nodes import _cfg, _span
from app.agent.state import AskGraphState
from config.settings import Settings, get_settings


# 问句中常见维度/指标词，用于列名启发式匹配
_DIMENSION_HINTS = (
    "年级",
    "班级",
    "项目",
    "学校",
    "日期",
    "时间",
    "月份",
    "周",
    "人数",
    "人次",
    "参与",
    "打卡",
    "占比",
    "排名",
    "趋势",
    "合计",
    "总计",
    "平均",
)


def _column_text(columns: list[str]) -> str:
    """列名拼接为小写文本，便于子串匹配。"""
    return " ".join(str(c) for c in columns).lower()


def _question_dimension_terms(question: str) -> list[str]:
    """从问句提取可能需要出现在结果列中的业务词。"""
    terms: list[str] = []
    for hint in _DIMENSION_HINTS:
        if hint in question:
            terms.append(hint)
    # 按「各X」「按X」抽取
    for m in re.finditer(r"(?:各|按)([\u4e00-\u9fff]{1,8})", question):
        term = m.group(1)
        if term and term not in terms:
            terms.append(term)
    return terms


def _expected_metrics_from_plan(plan: dict[str, Any] | None) -> list[str]:
    """从 Plan LLM 产出的 metrics 字段收集期望出现在结果列中的指标。"""
    if not plan:
        return []
    labels: list[str] = list(plan.get("metrics") or [])
    for step in plan.get("steps") or []:
        for m in step.get("metrics") or []:
            if m not in labels:
                labels.append(m)
    return labels


def _metric_reflected_in_columns(metric: str, columns: list[str]) -> bool:
    """指标是否在列名中有体现（列名须包含指标的关键子串，避免「运动个数」误判覆盖分项指标）。"""
    m = metric.strip()
    if not m:
        return True
    m_lower = m.lower()
    for col in columns:
        c = str(col)
        c_lower = c.lower()
        if m_lower == c_lower or m_lower in c_lower:
            return True
        # 去掉通用后缀后，关键片段须出现在列名中（长度≥2）
        core = (
            m_lower.replace("项目", "")
            .replace("个数", "")
            .replace("人数", "")
            .replace("运动", "")
            .strip()
        )
        if len(core) >= 2 and core in c_lower:
            return True
    return False


def verify_answer_heuristic(
    question: str,
    columns: list[str] | None,
    rows: list[list] | None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    规则验证：空结果 / 列名未覆盖问句维度词。

    Returns:
        {"passed": bool, "reason": str, "missing_terms": list, "row_count": int}
    """
    cols = columns or []
    row_list = rows or []
    row_count = len(row_list)

    if row_count == 0:
        return {
            "passed": False,
            "reason": "empty_result",
            "message": "查询结果为空，可能 WHERE 过严或关联条件错误",
            "missing_terms": [],
            "row_count": 0,
        }

    plan_metrics = _expected_metrics_from_plan(plan)
    if plan_metrics:
        missing_plan = [m for m in plan_metrics if not _metric_reflected_in_columns(m, cols)]
        if missing_plan:
            return {
                "passed": False,
                "reason": "missing_plan_metrics",
                "message": f"结果列未覆盖 plan 要求的指标：{', '.join(missing_plan[:6])}",
                "missing_terms": missing_plan,
                "row_count": row_count,
            }

    terms = _question_dimension_terms(question)
    if not terms:
        return {
            "passed": True,
            "reason": "ok",
            "message": "结果非空",
            "missing_terms": [],
            "row_count": row_count,
        }

    col_text = _column_text(cols)
    # 列名多为英文/SQL 字段名，中文维度词不一定出现在列名中；此处仅记录，不因此判定失败
    missing = [t for t in terms if t not in col_text]
    _ = missing  # 预留 span/LLM 参考，避免误触发 verify→correct 长循环

    return {
        "passed": True,
        "reason": "ok",
        "message": "结果非空（列名维度匹配仅作参考，不强制）",
        "missing_terms": missing,
        "row_count": row_count,
    }


async def _verify_with_llm(
    settings: Settings,
    question: str,
    columns: list[str],
    rows: list[list],
    heuristic: dict[str, Any],
) -> dict[str, Any]:
    """LLM 轻量二次确认（可选 Flag 开启时）。"""
    llm = build_llm(settings)
    sample_rows = rows[:3]
    system = (
        "你是问数结果质检员。根据用户问句、结果列名与样例行，判断结果是否回答了问句。"
        "输出 JSON：{\"passed\": true/false, \"reason\": \"简短说明\"}"
    )
    user = (
        f"问句：{question}\n"
        f"列名：{columns}\n"
        f"样例行：{json.dumps(sample_rows, ensure_ascii=False)[:1500]}\n"
        f"规则预判：{heuristic.get('message')}"
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            return heuristic
        parsed = json.loads(match.group(0))
        passed = bool(parsed.get("passed"))
        return {
            "passed": passed,
            "reason": parsed.get("reason") or heuristic.get("reason"),
            "message": parsed.get("reason") or heuristic.get("message"),
            "missing_terms": heuristic.get("missing_terms") or [],
            "row_count": heuristic.get("row_count", len(rows)),
            "llm_verified": True,
        }
    except Exception:
        return heuristic


async def verify_answer(state: AskGraphState, config: RunnableConfig) -> dict:
    """执行后语义验证，写入 verify_result / verify_passed。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]

    if state.get("error_code"):
        return {}

    if not settings.verify_answer_enabled:
        await _span(config, "verify_answer", t0, "degraded", {"skipped": True})
        return {"verify_passed": True, "verify_result": {"passed": True, "reason": "disabled"}}

    question = state.get("normalized_question") or state.get("question") or ""
    columns = state.get("columns") or []
    rows = state.get("rows") or []
    attempts = (state.get("verify_attempts") or 0) + 1

    heuristic = verify_answer_heuristic(
        question,
        columns,
        rows,
        plan=state.get("plan"),
    )
    result = heuristic
    if settings.verify_answer_llm_enabled and not heuristic.get("passed"):
        result = await _verify_with_llm(settings, question, columns, rows, heuristic)

    passed = bool(result.get("passed"))
    status = "success" if passed else "fail"
    sample = [list(r) for r in (rows or [])[:3]]
    await _span(
        config,
        "verify_answer",
        t0,
        status,
        {
            "passed": passed,
            "reason": result.get("reason"),
            "row_count": result.get("row_count"),
            "missing_terms": result.get("missing_terms"),
            "sample_rows": sample,
        },
    )

    update: dict[str, Any] = {
        "verify_passed": passed,
        "verify_result": result,
        "verify_attempts": attempts,
    }
    if not passed:
        update["validation_error"] = result.get("message") or "结果未通过语义验证"
        update["error_code"] = "VERIFY_FAILED"
        update["error_message"] = update["validation_error"]
    else:
        update["error_code"] = None
        update["error_message"] = None
        update["validation_error"] = None
    return update


def route_after_verify(state: AskGraphState) -> str:
    """
    验证通过 → build_chart → format_answer；
    失败且仍有修正预算 → correct_sql（最多 VERIFY_MAX_CORRECT 次，避免图步数耗尽）。
    """
    if state.get("verify_passed", True):
        return "build_chart"
    correct_count = state.get("correct_sql_count") or 0
    verify_attempts = state.get("verify_attempts") or 0
    settings = get_settings()
    max_correct = settings.agent_max_correct
    verify_cap = min(settings.verify_max_correct, max_correct)
    # verify 已跑过一轮修正后不再回 correct_sql，防止 verify↔execute 长链
    if verify_attempts <= verify_cap and correct_count < max_correct:
        return "correct_sql"
    return "format_answer"
