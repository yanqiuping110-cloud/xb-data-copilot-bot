"""
LLM 调用封装：DeepSeek 思考模式 + 流式 reasoning_content。

LangChain ChatOpenAI 不解析 delta.reasoning_content，思考模式流式输出走 OpenAI SDK。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from openai import AsyncOpenAI

from config.settings import Settings


def messages_to_api(messages: Sequence[BaseMessage]) -> list[dict[str, str]]:
    """LangChain Message → OpenAI chat messages。"""
    out: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            role = "system"
        elif isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        else:
            role = "user"
        content = msg.content
        text = content if isinstance(content, str) else str(content or "")
        out.append({"role": role, "content": text})
    return out


def thinking_request_body(settings: Settings) -> dict[str, Any]:
    """DeepSeek 思考模式请求体扩展。"""
    if not settings.llm_thinking_enabled:
        return {}
    body: dict[str, Any] = {"thinking": {"type": "enabled"}}
    effort = (settings.llm_reasoning_effort or "").strip()
    if effort:
        body["reasoning_effort"] = effort
    return body


def make_openai_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.llm_api_key or "ollama",
        base_url=settings.llm_api_base.rstrip("/"),
        timeout=settings.llm_timeout_sec,
    )


def _usage_tokens(usage: Any) -> tuple[int | None, int | None]:
    if usage is None:
        return None, None
    token_in = getattr(usage, "prompt_tokens", None)
    token_out = getattr(usage, "completion_tokens", None)
    return token_in, token_out


def _chat_create_kwargs(
    settings: Settings,
    messages: Sequence[BaseMessage],
    *,
    stream: bool = False,
) -> dict[str, Any]:
    """组装 chat.completions.create 参数（thinking 走 extra_body）。"""
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages_to_api(messages),
    }
    if stream:
        kwargs["stream"] = True
    extra = thinking_request_body(settings)
    if extra:
        kwargs["extra_body"] = extra
    return kwargs


async def _stream_openai_chat(
    settings: Settings,
    messages: Sequence[BaseMessage],
    *,
    content_queue: asyncio.Queue[str] | None = None,
    thinking_queue: asyncio.Queue[str] | None = None,
) -> tuple[str, str | None]:
    client = make_openai_client(settings)
    stream = await client.chat.completions.create(
        **_chat_create_kwargs(settings, messages, stream=True),
    )
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        rc = getattr(delta, "reasoning_content", None) or ""
        cc = getattr(delta, "content", None) or ""
        if rc:
            thinking_parts.append(rc)
            if thinking_queue is not None and settings.llm_thinking_stream:
                await thinking_queue.put(rc)
        if cc:
            content_parts.append(cc)
            if content_queue is not None:
                await content_queue.put(cc)
    reasoning = "".join(thinking_parts) or None
    return "".join(content_parts), reasoning


async def complete_messages(
    settings: Settings,
    messages: Sequence[BaseMessage],
    *,
    content_queue: asyncio.Queue[str] | None = None,
    thinking_queue: asyncio.Queue[str] | None = None,
) -> tuple[str, str | None, int | None, int | None]:
    """
    统一 LLM 调用入口。

    Returns:
        (content, reasoning_content, token_in, token_out)
    """
    use_openai = settings.llm_thinking_enabled or content_queue is not None or thinking_queue is not None
    want_stream = content_queue is not None or (
        thinking_queue is not None and settings.llm_thinking_stream
    )

    if use_openai and want_stream:
        content, reasoning = await _stream_openai_chat(
            settings,
            messages,
            content_queue=content_queue,
            thinking_queue=thinking_queue,
        )
        return content, reasoning, None, None

    if use_openai:
        client = make_openai_client(settings)
        resp = await client.chat.completions.create(
            **_chat_create_kwargs(settings, messages),
        )
        msg = resp.choices[0].message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None)
        token_in, token_out = _usage_tokens(resp.usage)
        if (
            reasoning
            and thinking_queue is not None
            and settings.llm_thinking_stream
        ):
            await thinking_queue.put(reasoning)
        return content, reasoning, token_in, token_out

    from app.agent.llm_sql import build_llm

    llm = build_llm(settings)
    resp = await llm.ainvoke(list(messages))
    content = resp.content if isinstance(resp.content, str) else str(resp.content or "")
    token_in = token_out = None
    meta = getattr(resp, "response_metadata", None) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    if usage:
        token_in = usage.get("prompt_tokens") or usage.get("input_tokens")
        token_out = usage.get("completion_tokens") or usage.get("output_tokens")
    return content, None, token_in, token_out
