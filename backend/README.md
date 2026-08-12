# 问数后端（FastAPI）

Python API 入口：`app/main.py`。环境变量与**虚拟环境**均在本目录：

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
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

测试：`pytest tests/ -q`（需先 `activate` 且 `APP_ENV=development`）。

问数链路：`/api/v1/ask` → **LangGraph**（`app/agent/`），L1 经知识库召回 + LLM 精选后注入规划；未命中时由 LLM 生成 SQL（Ollama 等，见 `.env`）。

问数语义种子（L1 样例 + 指标白名单，需已建 copilot 表）：

```powershell
# 已有库：先人工执行 scripts/sql/copilot/V003__sql_example_meta_json.sql
python scripts/seed_sql_examples.py
```

元数据知识库种子（首屏 + project_id 取值，需已执行 V004）：

```powershell
# 先人工执行 scripts/sql/copilot/V004__meta_knowledge.sql
python scripts/seed_semantic_meta.py
```

Zvec 混合召回索引（默认进程内；需 Ollama embedding + 元数据已注册）：

```powershell
python scripts/build_search_index.py
# 或 POST /api/v1/admin/meta/rebuild-index（ADMIN/OPERATOR JWT）
# 可选：VECTOR_STORE=elasticsearch 时使用 ES（见 .env.example）
```

数据库变更策略：[docs/90-DATABASE_CHANGE_POLICY.md](../docs/90-DATABASE_CHANGE_POLICY.md)  
问数库 DDL 版本目录：`scripts/sql/copilot/`（仅人工执行）。

详见仓库根目录 [README.md](../README.md)、[docs/01-MVP_DEVELOPMENT_PLAN.md](../docs/01-MVP_DEVELOPMENT_PLAN.md)（**§5.1 中文注释规范**）、[docs/02-PROGRESS.md](../docs/02-PROGRESS.md)。
