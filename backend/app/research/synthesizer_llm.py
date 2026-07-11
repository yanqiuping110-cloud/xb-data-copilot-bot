"""ReportDocument LLM 扩写（执行摘要、章导语、建议）。"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_sql import build_llm
from config.settings import Settings

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_json(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
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


def _section_brief(section_results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for sr in section_results:
        idx = sr.get("section_index")
        title = sr.get("title") or ""
        status = sr.get("status") or "fail"
        answer = (sr.get("answer") or "")[:500]
        row_n = len(sr.get("rows") or [])
        lines.append(f"- 第{idx}节「{title}」[{status}] 行数={row_n} 解读={answer}")
    return "\n".join(lines)


async def enrich_report_document(
    doc: dict[str, Any],
    *,
    plan: dict[str, Any],
    section_results: list[dict[str, Any]],
    scope_summary: str,
    settings: Settings,
) -> dict[str, Any]:
    """用 LLM 扩写报告文档；失败时返回原文档。"""
    if not settings.research_synthesizer_llm_enabled:
        return doc

    llm = build_llm(settings)
    title = plan.get("title") or doc.get("meta", {}).get("title") or "深度洞察报告"
    brief = _section_brief(section_results)
    system = (
        "你是企业数据分析报告主编。根据各章节问数结果，输出 JSON（不要 markdown 代码块外的文字）。"
        "字段：executiveSummaryParagraphs(字符串数组,2-4段)、"
        "chapterNarratives(对象,键为章节index字符串,值为2-4句章导语)、"
        "chapterBullets(对象,键为章节index,值为3-5条要点字符串数组)、"
        "findings(数组,每项含type/text/chapterIndex)、"
        "recommendations(字符串数组,4-6条可行动建议)。"
        "禁止编造数据；失败章节如实说明并给出排查建议。"
    )
    user = (
        f"报告标题：{title}\n数据范围：{scope_summary}\n\n各节结果：\n{brief}\n\n"
        "请生成完整 JSON。"
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed = _extract_json(content)
        if not parsed:
            return doc
    except Exception:
        return doc

    if paras := parsed.get("executiveSummaryParagraphs"):
        if isinstance(paras, list):
            doc["executiveSummary"] = {
                "paragraphs": [str(p).strip() for p in paras if str(p).strip()]
            }

    narratives = parsed.get("chapterNarratives") or {}
    bullets_map = parsed.get("chapterBullets") or {}
    if isinstance(narratives, dict):
        for ch in doc.get("chapters") or []:
            key = str(ch.get("index"))
            if narrative := narratives.get(key):
                ch["narrative"] = str(narrative).strip()
            if bl := bullets_map.get(key):
                if isinstance(bl, list):
                    ch["bullets"] = [str(b).strip() for b in bl if str(b).strip()]

    if findings := parsed.get("findings"):
        if isinstance(findings, list):
            doc["findings"] = [
                {
                    "type": f.get("type") or "info",
                    "text": str(f.get("text") or "")[:240],
                    "chapterIndex": f.get("chapterIndex"),
                }
                for f in findings
                if isinstance(f, dict) and f.get("text")
            ][:10]

    if recs := parsed.get("recommendations"):
        if isinstance(recs, list):
            doc["recommendations"] = [str(r).strip() for r in recs if str(r).strip()][:8]

    return doc
