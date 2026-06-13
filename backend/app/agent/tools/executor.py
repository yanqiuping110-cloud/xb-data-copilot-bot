"""
工具执行器：统一注册、调用并写入 span（§11.7.2 / §11.7.5）。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.nodes import _span
from app.agent.tools.meta_tools import describe_table, get_join_path, list_relations
from app.agent.tools.probe_tools import run_probe_sql
from app.agent.tools.code_tools import (
    get_code_artifact,
    link_artifact_to_meta,
    search_code_artifacts,
    trace_code_flow,
)
from app.agent.tools.search_tools import (
    search_field_values,
    search_metrics,
    search_sql_examples,
)
from app.core.context import UserContext
from config.settings import Settings

# 工具名 → 实现；禁止写库
ToolFn = Callable[..., Awaitable[dict[str, Any]]]

TOOL_REGISTRY: dict[str, ToolFn] = {
    "describe_table": describe_table,
    "list_relations": list_relations,
    "get_join_path": get_join_path,
    "search_metrics": search_metrics,
    "search_field_values": search_field_values,
    "search_sql_examples": search_sql_examples,
    "run_probe_sql": run_probe_sql,
    "search_code_artifacts": search_code_artifacts,
    "get_code_artifact": get_code_artifact,
    "trace_code_flow": trace_code_flow,
    "link_artifact_to_meta": link_artifact_to_meta,
}


def tool_span_name(tool_name: str) -> str:
    """LangGraph span 节点名：tool_<name>。"""
    return f"tool_{tool_name}"


async def execute_tool_span(
    config: RunnableConfig,
    *,
    tool_name: str,
    args: dict[str, Any],
    session: AsyncSession,
    settings: Settings,
    ctx: UserContext,
    question: str,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """
    执行单个工具并写 span。

    Returns:
        工具 JSON 结果；未知工具或异常时含 error 字段。
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        result = {"error": "UNKNOWN_TOOL", "tool": tool_name}
        await _span(
            config,
            tool_span_name(tool_name),
            time.perf_counter(),
            "fail",
            {"tool": tool_name, "args": args, "error": "UNKNOWN_TOOL"},
        )
        return result

    t0 = time.perf_counter()
    try:
        if tool_name == "describe_table":
            result = await fn(session, settings, table=args.get("table", ""))
        elif tool_name == "list_relations":
            result = await fn(session, settings, table=args.get("table"))
        elif tool_name == "get_join_path":
            result = await fn(
                session,
                settings,
                from_table=args.get("from_table", ""),
                to_table=args.get("to_table", ""),
            )
        elif tool_name in ("search_metrics", "search_field_values"):
            result = await fn(
                session,
                settings,
                query=args.get("query") or question,
                keywords=keywords,
            )
        elif tool_name == "search_sql_examples":
            result = await fn(
                session,
                settings,
                query=args.get("query") or question,
                ctx=ctx,
            )
        elif tool_name == "run_probe_sql":
            result = await fn(
                session,
                settings,
                ctx=ctx,
                sql=args.get("sql", ""),
            )
        elif tool_name == "search_code_artifacts":
            result = await fn(
                session,
                settings,
                query=args.get("query") or question,
                keywords=keywords,
            )
        elif tool_name == "get_code_artifact":
            result = await fn(session, settings, artifact_id=int(args.get("artifact_id", 0)))
        elif tool_name == "trace_code_flow":
            result = await fn(
                session,
                settings,
                symbol_or_path=args.get("symbol_or_path") or args.get("query") or "",
                repo_id=args.get("repo_id"),
            )
        elif tool_name == "link_artifact_to_meta":
            result = await fn(session, settings, artifact_id=int(args.get("artifact_id", 0)))
        else:
            result = await fn(session, settings, **args)

        status = "fail" if result.get("error") else "success"
        preview = _result_preview(result)
        await _span(
            config,
            tool_span_name(tool_name),
            t0,
            status,
            {
                "tool": tool_name,
                "args": _sanitize_args(args),
                "result_preview": preview,
            },
        )
        return result
    except Exception as exc:
        await _span(
            config,
            tool_span_name(tool_name),
            t0,
            "fail",
            {
                "tool": tool_name,
                "args": _sanitize_args(args),
                "error": str(exc)[:300],
            },
        )
        return {"error": "TOOL_EXEC_ERROR", "message": str(exc), "tool": tool_name}


def _sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    """截断参数摘要，避免 trace 过大。"""
    out: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 120:
            out[key] = value[:120] + "..."
        else:
            out[key] = value
    return out


def _result_preview(result: dict[str, Any]) -> str:
    if result.get("error"):
        return str(result.get("error"))
    if "count" in result:
        return f"count={result['count']}"
    if "hops" in result:
        return f"hops={result['hops']}"
    if "column_count" in result:
        return f"columns={result['column_count']}"
    return "ok"


class ToolExecutor:
    """批量执行 plan 步骤声明的工具。"""

    def __init__(
        self,
        config: RunnableConfig,
        *,
        session: AsyncSession,
        settings: Settings,
        ctx: UserContext,
        question: str,
        keywords: list[str] | None = None,
    ) -> None:
        self._config = config
        self._session = session
        self._settings = settings
        self._ctx = ctx
        self._question = question
        self._keywords = keywords or []
        self.observations: list[dict[str, Any]] = []

    async def run_tools(
        self,
        tool_names: list[str],
        *,
        default_tables: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """按工具名列表依次执行（去重），追加 observation。"""
        seen: set[str] = set()
        tables = default_tables or []
        for name in tool_names:
            if name in seen:
                continue
            seen.add(name)
            args = self._default_args(name, tables)
            result = await execute_tool_span(
                self._config,
                tool_name=name,
                args=args,
                session=self._session,
                settings=self._settings,
                ctx=self._ctx,
                question=self._question,
                keywords=self._keywords,
            )
            obs = {"tool": name, "args": args, "result": result}
            self.observations.append(obs)
        return self.observations

    def _default_args(self, tool_name: str, tables: list[str]) -> dict[str, Any]:
        """plan 雏形：按种子召回表推断工具参数。"""
        if tool_name == "describe_table" and tables:
            return {"table": tables[0]}
        if tool_name == "list_relations" and tables:
            return {"table": tables[0]}
        if tool_name == "get_join_path" and len(tables) >= 2:
            return {"from_table": tables[0], "to_table": tables[1]}
        if tool_name in ("search_metrics", "search_field_values", "search_sql_examples"):
            return {"query": self._question}
        if tool_name == "search_code_artifacts":
            return {"query": self._question}
        return {}
