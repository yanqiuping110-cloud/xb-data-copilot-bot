# MCP Server

通过 stdio 暴露问数工具，供 Cursor / Agent 调用。

## 配置

```bash
MCP_ENABLED=true
MCP_API_KEY=<长期 JWT 或专用 service token>
MCP_API_BASE=http://127.0.0.1:8000
```

`MCP_API_KEY` 应对应一个有问数权限的用户 JWT（或后续扩展的 service account）。

## Cursor 配置示例

`.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "data-copilot": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "backend",
      "env": {
        "MCP_ENABLED": "true",
        "MCP_API_KEY": "your-jwt",
        "MCP_API_BASE": "http://127.0.0.1:8000"
      }
    }
  }
}
```

## 工具列表

| 工具 | 说明 |
|------|------|
| `copilot_ask` | 自然语言问数，`question` 必填 |
| `copilot_list_sessions` | 最近会话列表 |
| `copilot_research` | 提交深度分析报告 |

## 启动验证

```bash
cd backend
python -m app.mcp.server
```

stdio 模式，由 MCP 客户端拉起；单独运行时会等待 JSON-RPC 输入。

## 安全

- 继承 `ASK_RATE_LIMIT` 等问数限流
- 勿将 MCP_API_KEY 提交到版本库
- 生产建议独立 service 账户 + 只读/Scoped JWT
