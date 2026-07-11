"""ReportDocument 合成。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.research.theme import accent_for_intent, load_theme


def _charts_for_section(sr: dict[str, Any]) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    png = sr.get("chart_png_path")
    if png:
        charts.append({"caption": sr.get("title") or "图表", "pngPath": png})
    spec = sr.get("chart_spec")
    if spec and not png:
        charts.append({"chartSpecRef": f"section_{sr.get('section_index')}", "caption": spec.get("title") or "图表"})
    return charts


def synthesize_report_document(
    *,
    report_id: str,
    plan: dict[str, Any],
    section_results: list[dict[str, Any]],
    scope_summary: str,
    theme_name: str = "default",
) -> dict[str, Any]:
    """将各节 ask 结果合成为 ReportDocument JSON。"""
    theme = load_theme(theme_name)
    title = plan.get("title") or "深度洞察报告"
    chapters: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []

    for sr in section_results:
        idx = int(sr.get("section_index") or 0)
        intent = sr.get("intent") or "open_query"
        status = sr.get("status") or "fail"
        answer = sr.get("answer") or ""
        columns = sr.get("columns") or []
        rows = sr.get("rows") or []
        max_rows = 50
        truncated = len(rows) > max_rows
        display_rows = rows[:max_rows]

        tables = []
        if columns and rows:
            tables.append(
                {
                    "caption": f"{sr.get('title', '')} 数据明细",
                    "columns": columns,
                    "rows": display_rows,
                    "truncated": truncated,
                    "totalRows": len(rows),
                }
            )

        bullets: list[str] = []
        if status == "success" and answer:
            for line in answer.split("\n"):
                line = line.strip().lstrip("•-* ")
                if line:
                    bullets.append(line)
            if not bullets:
                bullets.append(answer)
        elif status != "success":
            bullets.append(f"本节数据暂不可用（{sr.get('error_code') or status}）")

        chapters.append(
            {
                "index": idx,
                "title": sr.get("title") or f"第{idx}章",
                "intent": intent,
                "accent": accent_for_intent(theme, intent),
                "narrative": answer if status == "success" else "数据暂不可用，请稍后重试或调整问法。",
                "tables": tables,
                "charts": _charts_for_section(sr),
                "bullets": bullets,
                "status": status,
            }
        )

        if status == "success" and answer and len(answer) > 10:
            findings.append(
                {
                    "type": "up" if "增" in answer or "升" in answer else "info",
                    "text": answer[:240],
                    "chapterIndex": idx,
                }
            )

        traces.append(
            {
                "chapterIndex": idx,
                "traceId": sr.get("sub_trace_id"),
                "status": status,
                "latencyMs": sr.get("latency_ms"),
            }
        )

    success_n = sum(1 for s in section_results if s.get("status") == "success")
    summary_paras = [
        f"本报告共 {len(section_results)} 个分析章节，成功 {success_n} 节。",
        f"数据范围：{scope_summary}。",
        plan.get("title") or "",
    ]
    recommendations = _default_recommendations(section_results)

    page_estimate = max(15, 3 + len(chapters) * 2 + len(recommendations))

    return {
        "meta": {
            "title": title,
            "reportId": report_id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "scopeSummary": scope_summary,
            "pageEstimate": page_estimate,
            "theme": theme_name,
        },
        "executiveSummary": {"paragraphs": [p for p in summary_paras if p.strip()]},
        "chapters": chapters,
        "findings": findings[:8],
        "recommendations": recommendations,
        "appendix": {"traces": traces, "metricRefs": []},
    }


def _default_recommendations(section_results: list[dict[str, Any]]) -> list[str]:
    recs = [
        "持续关注核心 KPI 的周环比与月环比变化。",
        "对异常偏离指标建立运营复盘机制。",
        "将高频问句沉淀为 L1 样例以提升响应稳定性。",
    ]
    failed = [s for s in section_results if s.get("status") != "success"]
    if failed:
        recs.append(f"有 {len(failed)} 个章节未能完成查询，建议检查权限或元数据配置。")
    return recs[:8]
