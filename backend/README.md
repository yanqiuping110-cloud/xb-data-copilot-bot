# 问数后端（FastAPI）

Python API 入口：`app/main.py`。环境变量、**虚拟环境**均在本目录：

| 路径 | 说明 |
|------|------|
| `backend/.venv/` | Python 虚拟环境（`gitignore`） |
| `backend/.env.development` | 本机配置（`gitignore`） |
| `backend/.env.example` | 配置模板 |

```powershell
# 在 backend/ 目录执行
copy .env.example .env.development
$env:APP_ENV = "development"
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

测试：`pytest tests/ -q`（需已 `activate` 且 `APP_ENV=development`）。

问数链路：`/api/v1/ask` 经 **LangGraph 7 节点**（`app/agent/`），L1 未命中时调用 `.env` 中 **LLM**（Ollama 等）。

问数语义种子（L1 样例 + 指标白名单，需已建 copilot 表）：

```powershell
# 已有库：先人工执行 scripts/sql/copilot/V003__sql_example_meta_json.sql
python scripts/seed_sql_examples.py
```

数据库变更策略：[docs/DATABASE_CHANGE_POLICY.md](../docs/DATABASE_CHANGE_POLICY.md)  
问数库 DDL 版本目录：`scripts/sql/copilot/`（仅人工执行）

详见仓库根目录 [README.md](../README.md)、[docs/DEVELOPMENT_PLAN.md](../docs/DEVELOPMENT_PLAN.md)（**§5.1 中文注释规范**）、[docs/PROGRESS.md](../docs/PROGRESS.md)。
