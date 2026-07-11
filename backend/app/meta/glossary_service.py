"""术语库问句匹配与 Prompt 格式化。"""

from __future__ import annotations

import re

from app.meta.glossary_repository import GlossaryRepository, GlossaryTermRow
from app.security.prompt_boundary import sanitize_recall_text


def match_glossary_terms(
    question: str,
    terms: list[GlossaryTermRow],
    *,
    top_k: int = 5,
) -> list[GlossaryTermRow]:
    """按问句子串匹配已发布术语（长词优先）。"""
    q = (question or "").strip()
    if not q or not terms:
        return []
    matched: list[GlossaryTermRow] = []
    for row in terms:
        term = (row.term or "").strip()
        if len(term) >= 2 and term in q:
            matched.append(row)
        if len(matched) >= top_k:
            break
    return matched


def suggest_terms_from_question(question: str, *, max_terms: int = 5) -> list[dict]:
    """从 badcase 问句抽取术语候选（运营审核用）。"""
    q = (question or "").strip()
    if not q:
        return []
    # 中文连续片段 + 英文词
    chunks = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z]{3,}", q)
    seen: set[str] = set()
    out: list[dict] = []
    for c in chunks:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"term": c, "canonicalName": c, "definition": f"来自问句：{q[:120]}"})
        if len(out) >= max_terms:
            break
    return out


def format_glossary_prompt_lines(
    matched: list[GlossaryTermRow],
    *,
    sanitize: bool = True,
) -> list[str]:
    """格式化为 LLM Prompt 术语对齐块。"""
    if not matched:
        return []
    lines = ["【术语对齐（业务别名 → 标准表述）】"]
    for row in matched:
        definition = row.definition or ""
        if sanitize and definition:
            definition, _ = sanitize_recall_text(definition, enabled=True)
        canonical = row.canonical_name
        if sanitize:
            canonical, _ = sanitize_recall_text(canonical, enabled=True)
        line = f"- 「{row.term}」→ {canonical}"
        if definition:
            line += f"（{definition[:120]}）"
        if row.ref_type != "concept":
            line += f" [{row.ref_type}]"
        lines.append(line)
    lines.append("")
    return lines


async def recall_glossary_for_question(
    repo: GlossaryRepository,
    question: str,
    *,
    scope_role: str | None = None,
    top_k: int = 5,
) -> list[GlossaryTermRow]:
    """加载已发布术语并匹配问句。"""
    terms = await repo.list_published_for_recall(scope_role=scope_role)
    return match_glossary_terms(question, terms, top_k=top_k)
