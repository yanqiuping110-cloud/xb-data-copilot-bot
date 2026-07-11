"""分析意图 → 章节计划（启发式 + 模板）。"""

from __future__ import annotations

import re
from typing import Any

TEMPLATE_SECTIONS: dict[str, list[dict[str, Any]]] = {
    "monthly_ops": [
        {"title": "总体 KPI 概览", "question": "本月核心指标总体汇总", "intent": "trend"},
        {"title": "时间趋势", "question": "最近7天每日核心指标趋势", "intent": "trend"},
        {"title": "维度对比", "question": "本月各维度核心指标对比", "intent": "compare"},
        {"title": "结论与建议", "question": "本月异常指标与偏离项汇总", "intent": "anomaly"},
    ],
    "monthly_ops_long": [
        {"title": "总体 KPI 概览", "question": "本月核心指标总体汇总", "intent": "trend"},
        {"title": "时间趋势", "question": "最近7天每日核心指标趋势", "intent": "trend"},
        {"title": "产品线对比", "question": "本月各产品线核心指标对比", "intent": "compare"},
        {"title": "区域维度", "question": "本月各区域核心指标分布", "intent": "rank"},
        {"title": "结构占比", "question": "本月核心指标结构占比", "intent": "share"},
        {"title": "异常偏离", "question": "本月异常与偏离指标", "intent": "anomaly"},
        {"title": "同比环比", "question": "本月与上月核心指标对比", "intent": "compare"},
        {"title": "行动建议", "question": "基于本月数据的改进方向", "intent": "open_query"},
    ],
    "period_compare": [
        {"title": "本期概览", "question": "本期核心指标汇总", "intent": "trend"},
        {"title": "上期对比", "question": "本期与上期核心指标对比", "intent": "compare"},
        {"title": "变化 Top", "question": "本期变化最大的指标排名", "intent": "rank"},
    ],
}


def _title_from_request(request_text: str) -> str:
    text = (request_text or "").strip()
    if len(text) <= 40:
        return text or "深度洞察报告"
    return text[:40].rstrip() + "…"


def build_research_plan(
    request_text: str,
    *,
    template_code: str | None = None,
    max_sections: int = 12,
) -> dict[str, Any]:
    """生成 research plan（不调用 LLM，保证单测稳定）。"""
    code = (template_code or "monthly_ops").strip() or "monthly_ops"
    if code == "custom" or code not in TEMPLATE_SECTIONS:
        sections_raw = _parse_custom_sections(request_text, max_sections)
        if not sections_raw:
            sections_raw = TEMPLATE_SECTIONS["monthly_ops"]
        else:
            sections_raw = sections_raw[:max_sections]
    else:
        sections_raw = list(TEMPLATE_SECTIONS[code])[:max_sections]

    sections: list[dict[str, Any]] = []
    for i, s in enumerate(sections_raw, start=1):
        sections.append(
            {
                "index": i,
                "title": s["title"],
                "question": s.get("question") or s["title"],
                "intent": s.get("intent") or "open_query",
                "visualization": {"enabled": True, "preferred_types": ["line", "bar"]},
            }
        )

    return {
        "title": _title_from_request(request_text),
        "templateCode": code,
        "sections": sections,
        "synthesis_hints": ["突出关键变化", "给出可行动建议"],
    }


def _parse_custom_sections(request_text: str, max_sections: int) -> list[dict[str, Any]]:
    """从顿号/逗号/换行拆分子任务。"""
    parts = re.split(r"[；;、,\n]+", request_text or "")
    out: list[dict[str, Any]] = []
    for p in parts:
        p = p.strip()
        if len(p) < 4:
            continue
        intent = "trend" if any(k in p for k in ("趋势", "每日", "7天")) else "compare"
        if any(k in p for k in ("异常", "建议", "结论")):
            intent = "anomaly"
        out.append({"title": p[:32], "question": p, "intent": intent})
        if len(out) >= max_sections:
            break
    return out
