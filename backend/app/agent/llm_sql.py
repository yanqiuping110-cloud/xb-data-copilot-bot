"""
LLM 生成 SQL：OpenAI 兼容 API（本机 Ollama 等）。
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.policy.role_policy import LLM_JOIN_ALIAS_SYSTEM_HINT
from config.settings import Settings

_SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*([\s\S]*?)```", re.IGNORECASE)
_SELECT_RE = re.compile(r"(SELECT[\s\S]+)", re.IGNORECASE)


def _extract_sql(text: str) -> str | None:
    """从模型输出中提取 SELECT 语句。"""
    stripped = text.strip()
    block = _SQL_BLOCK_RE.search(stripped)
    if block:
        candidate = block.group(1).strip()
    else:
        candidate = stripped
    if candidate.upper().startswith("SELECT"):
        return candidate.rstrip(";").strip()
    match = _SELECT_RE.search(candidate)
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
        "你是企业问数系统的 SQL 生成助手，只为智慧体育业务库生成只读查询。"
        "严格遵守上下文中的表白名单与 MySQL 5.7 语法。"
        "只能使用上下文中【候选表字段清单】列出的真实列名，禁止编造任何字段。"
        "SELECT 列别名优先使用中文（如 AS 学生名、AS 入学年份）；"
        "仅当用户明确要求英文表头时才使用英文别名。"
        f"{LLM_JOIN_ALIAS_SYSTEM_HINT}"
    )
    user_parts = [context_text, "", f"用户问题：{question}"]
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
