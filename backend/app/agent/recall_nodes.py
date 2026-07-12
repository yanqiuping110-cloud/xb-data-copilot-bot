"""
LangGraph 多阶段召回节点：关键词 → 表/字段/指标召回 → 合并定稿 → 构建 LLM 上下文。
"""

from __future__ import annotations

import time

from langchain_core.runnables import RunnableConfig

from app.agent.context_builder import (
    MergedRecallContext,
    build_llm_context_text,
    enrich_tables_from_mysql,
    finalize_kb_recall,
    merge_retrieved_info,
    span_detail_from_merged,
)
from app.agent.nodes import _cfg, _span
from app.agent.state import AskGraphState
from app.meta.repository import MetaRepository
from app.policy.role_policy import build_role_context_header
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.keyword_extractor import extract_keywords
from app.sql.whitelist import get_allowed_tables
from config.settings import Settings


def _get_merged(state: AskGraphState) -> MergedRecallContext | None:
    raw = state.get("merged_recall")
    if raw is None:
        return None
    if isinstance(raw, MergedRecallContext):
        return raw
    return None


async def extract_keywords_node(state: AskGraphState, config: RunnableConfig) -> dict:
    """从问句抽取关键词，供混合召回使用。"""
    t0 = time.perf_counter()
    question = (
        state.get("recall_question")
        or state.get("normalized_question")
        or state.get("question")
        or ""
    )
    keywords = extract_keywords(question)
    await _span(config, "extract_keywords", t0, "success", {"keywords": keywords, "count": len(keywords)})
    return {"keywords": keywords}


async def recall_tables(state: AskGraphState, config: RunnableConfig) -> dict:
    """表级向量/关键词召回。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    keywords = state.get("keywords") or []

    retriever = HybridRetriever(c["copilot_session"], settings)
    try:
        tables, recall_mode = await retriever.recall_tables_only(question, keywords)
        status = "success" if tables else "empty"
        detail = {
            "count": len(tables),
            "recall_mode": recall_mode,
            "items": [
                {"table": t.table_name, "score": t.score}
                for t in tables[:10]
            ],
        }
        await _span(config, "recall_tables", t0, status, detail)
        return {"recall_tables": tables, "recall_mode": recall_mode}
    finally:
        await retriever.close()


async def recall_columns(state: AskGraphState, config: RunnableConfig) -> dict:
    """字段向量/关键词召回（限定在表级召回候选内）。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    keywords = state.get("keywords") or []
    table_scope = [t.table_name for t in (state.get("recall_tables") or [])]

    retriever = HybridRetriever(c["copilot_session"], settings)
    try:
        columns, recall_mode = await retriever.recall_columns_only(
            question,
            keywords,
            table_names=table_scope or None,
        )
        status = "success" if columns else "empty"
        detail = {
            "count": len(columns),
            "recall_mode": recall_mode,
            "scope_tables": table_scope[:10],
            "items": [
                {"table": col.table_name, "column": col.column_name, "score": col.score}
                for col in columns[:8]
            ],
        }
        await _span(config, "recall_columns", t0, status, detail)
        return {"recall_columns": columns, "recall_mode": recall_mode}
    finally:
        await retriever.close()


async def recall_metrics(state: AskGraphState, config: RunnableConfig) -> dict:
    """指标向量/关键词召回。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    keywords = state.get("keywords") or []

    retriever = HybridRetriever(c["copilot_session"], settings)
    try:
        metrics = await retriever.recall_metrics_only(question, keywords)
        status = "success" if metrics else "empty"
        detail = {
            "count": len(metrics),
            "items": [{"code": m.metric_code, "score": m.score} for m in metrics[:5]],
        }
        await _span(config, "recall_metrics", t0, status, detail)
        return {"recall_metrics": metrics}
    finally:
        await retriever.close()


async def recall_field_values(state: AskGraphState, config: RunnableConfig) -> dict:
    """字段取值全文/关键词召回。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = state.get("normalized_question") or ""
    keywords = state.get("keywords") or []

    retriever = HybridRetriever(c["copilot_session"], settings)
    try:
        values = await retriever.recall_field_values_only(question, keywords)
        status = "success" if values else "empty"
        detail = {
            "count": len(values),
            "items": [
                {"table": v.table_name, "column": v.column_name, "value": v.value_text}
                for v in values[:5]
            ],
        }
        await _span(config, "recall_field_values", t0, status, detail)
        return {"recall_field_values": values}
    finally:
        await retriever.close()


async def merge_retrieved_info_node(state: AskGraphState, config: RunnableConfig) -> dict:
    """合并多路召回结果（含代码 artifact）。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    from app.retrieval.hybrid import HybridRecallResult, HybridRetriever

    retriever = HybridRetriever(c["copilot_session"], settings)
    code_items = []
    code_mode = "disabled"
    try:
        question = state.get("normalized_question") or ""
        keywords = state.get("keywords") or []
        if settings.code_knowledge_enabled:
            code_items, code_mode = await retriever.recall_code_artifacts(question, keywords)
    finally:
        await retriever.close()

    recall = HybridRecallResult(
        keywords=state.get("keywords") or [],
        tables=state.get("recall_tables") or [],
        columns=state.get("recall_columns") or [],
        metrics=state.get("recall_metrics") or [],
        field_values=state.get("recall_field_values") or [],
        code_artifacts=code_items,
        recall_mode=state.get("recall_mode") or "hybrid",
    )
    merged = merge_retrieved_info(recall)
    repo = MetaRepository(c["copilot_session"])
    merged = await finalize_kb_recall(merged, repo, settings)
    await _span(
        config,
        "merge_retrieved_info",
        t0,
        "success",
        {
            "table_count": len(merged.recalled_tables),
            "column_count": len(merged.columns),
            "metric_count": len(merged.metrics),
            "value_count": len(merged.field_values),
            "code_recall_count": len(code_items),
            "code_recall_mode": code_mode,
            "table_names": merged.table_names,
            "prompt_column_counts": {k: len(v) for k, v in merged.prompt_columns.items()},
        },
    )
    return {"merged_recall": merged, "recall_code_artifacts": code_items}


async def build_llm_context(state: AskGraphState, config: RunnableConfig) -> dict:
    """拼装结构化 Prompt 上下文，替代基线 retrieve_context。"""
    t0 = time.perf_counter()
    c = _cfg(config)
    settings: Settings = c["settings"]
    question = (
        state.get("recall_question")
        or state.get("normalized_question")
        or state.get("question")
        or ""
    )
    merged = _get_merged(state)

    try:
        if merged is not None:
            repo = MetaRepository(c["copilot_session"])
            merged = await enrich_tables_from_mysql(merged, repo)
            context_text = await build_llm_context_text(
                question,
                merged,
                c["copilot_session"],
                c["ctx"],
                settings=settings,
                memory_prompt_text=state.get("memory_prompt_text") or "",
            )
            detail = span_detail_from_merged(merged)
            detail["chars"] = len(context_text)
            status = "success"
        else:
            ctx = c["ctx"]
            allowed = ", ".join(sorted(get_allowed_tables())) or "（未配置）"
            context_text = (
                f"{build_role_context_header(ctx, settings=settings)}\n\n"
                f"【检索失败，仅依赖表白名单】\n{allowed}\n"
            )
            detail = {"chars": len(context_text)}
            status = "degraded"

        await _span(config, "build_llm_context", t0, status, detail)
        return {"context_text": context_text, "merged_recall": merged}
    except Exception as exc:
        context_text = "【检索失败，仅依赖表白名单】\n" + str(exc)
        await _span(config, "build_llm_context", t0, "degraded", {"error": str(exc)})
        return {"context_text": context_text}
