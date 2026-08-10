"""流式问数：节点开始时推送 progress(status=running)。"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from app.agent.streaming import progress_event


class AskNodeStartProgressCallback(AsyncCallbackHandler):
    """
    捕获 LangGraph 节点 on_chain_start，写入统一出口队列。

    过滤嵌套 LLM/工具链：仅当 runnable name 与 langgraph_node 一致时触发。
    """

    def __init__(self, out_queue: asyncio.Queue[tuple[str, Any]]) -> None:
        super().__init__()
        self._out = out_queue
        self._emitted: set[UUID] = set()

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _ = serialized, inputs, parent_run_id, tags
        if run_id in self._emitted:
            return
        meta = metadata or {}
        node = meta.get("langgraph_node")
        if not node or not isinstance(node, str):
            return
        name = kwargs.get("name") or node
        if name != node:
            return
        if node in ("LangGraph", "__start__", "__end__"):
            return
        self._emitted.add(run_id)
        await self._out.put(("sse", progress_event(node, status="running")))
