"""
MCP stdio 服务：对外暴露 copilot_ask / copilot_list_sessions。

启动：cd backend && python -m app.mcp.server
Cursor 配置见 docs/94-MCP.md
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx


def _api_base() -> str:
    return os.getenv("MCP_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def _api_key() -> str:
    return os.getenv("MCP_API_KEY", "")


def _auth_headers(token: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def copilot_ask(question: str, session_id: str | None = None) -> dict[str, Any]:
    """调用 REST 问数接口。"""
    body: dict[str, Any] = {"question": question}
    if session_id:
        body["sessionId"] = session_id
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{_api_base()}/api/v1/ask",
            json=body,
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def copilot_list_sessions() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_api_base()}/api/v1/sessions",
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def copilot_research(request_text: str, template_code: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"requestText": request_text}
    if template_code:
        body["templateCode"] = template_code
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_api_base()}/api/v1/research/report",
            json=body,
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "copilot_ask",
            "description": "自然语言问数，返回 answer、表格与 chartSpec",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "sessionId": {"type": "string"},
                },
                "required": ["question"],
            },
        },
        {
            "name": "copilot_list_sessions",
            "description": "列出最近问数会话",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "copilot_research",
            "description": "提交深度分析报告任务",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requestText": {"type": "string"},
                    "templateCode": {"type": "string"},
                },
                "required": ["requestText"],
            },
        },
    ]


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "copilot_ask":
        return await copilot_ask(
            question=str(arguments.get("question", "")),
            session_id=arguments.get("sessionId"),
        )
    if name == "copilot_list_sessions":
        return await copilot_list_sessions()
    if name == "copilot_research":
        return await copilot_research(
            request_text=str(arguments.get("requestText", "")),
            template_code=arguments.get("templateCode"),
        )
    raise ValueError(f"unknown tool: {name}")


async def _run_stdio_mcp() -> None:
    """极简 MCP JSON-RPC（stdio）— 兼容 Cursor tools/list + tools/call。"""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            msg = json.loads(line.decode())
        except json.JSONDecodeError:
            continue
        req_id = msg.get("id")
        method = msg.get("method", "")
        result: Any = None
        error: dict | None = None

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "data-copilot", "version": "0.1.0"},
                }
            elif method == "tools/list":
                result = {"tools": _tool_definitions()}
            elif method == "tools/call":
                params = msg.get("params") or {}
                name = params.get("name", "")
                args = params.get("arguments") or {}
                data = await _dispatch_tool(name, args)
                result = {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                }
            else:
                error = {"code": -32601, "message": f"Method not found: {method}"}
        except Exception as exc:
            error = {"code": -32000, "message": str(exc)}

        out: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error:
            out["error"] = error
        else:
            out["result"] = result
        writer.write((json.dumps(out, ensure_ascii=False) + "\n").encode())
        await writer.drain()


def main() -> None:
    if os.getenv("MCP_ENABLED", "false").lower() not in ("1", "true", "yes"):
        print("MCP_ENABLED 未开启，仍可在开发模式运行", file=sys.stderr)
    asyncio.run(_run_stdio_mcp())


if __name__ == "__main__":
    main()
