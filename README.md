# 小奔智慧体育 · 智能问数（Data Copilot）

企业级自然语言问数：Python FastAPI + Vue3 + LangGraph + MySQL 5.7。

详细设计见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)。  
开发进度见 [docs/PROGRESS.md](docs/PROGRESS.md)。  
**代码注释**：业务代码须写**中文注释**（见开发计划 §5.1）。

## 仓库结构

```text
data-copilot-bot/
├── backend/          # Python 问数 API（FastAPI）
├── frontend/         # Vue3 + Vite 问数前端
└── docs/               # 设计与规范
```

## 环境要求

| 组件 | 说明 |
|------|------|
| MySQL 5.7 | 宿主机/公司库：`sport`（只读）+ `copilot`（问数库） |
| Docker | RAGFlow + ES + Redis + MinIO（可选） |
| Ollama | 宿主机 LLM |
| Python 3.10+ | 后端 |
| Node.js 18+ | 前端 |

## 快速开始（本机）

### 后端

> **Python 虚拟环境放在 `backend/.venv/`**（不要在仓库根目录建 venv）。若根目录仍有迁移前的 `.venv`，可删掉后在 `backend` 下重建。

```powershell
cd backend
copy .env.example .env.development
# 编辑 MySQL、JWT 等

$env:APP_ENV = "development"
python -m venv .venv          # → backend\.venv
.\.venv\Scripts\activate
pip install -e ".[dev]"

mysql -u root -p < scripts/ddl_copilot.sql   # 表名均为 copilot_* 前缀，字段带 COMMENT
python scripts/seed_admin.py
# 若曾用旧表名，可执行 scripts/migrate_tables_to_copilot_prefix.sql

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：`/health`、`/ready`

### 前端

```powershell
cd frontend
copy .env.example .env.development
npm install
npm run dev
```

浏览器打开 <http://127.0.0.1:5173>（Vite 默认端口）。

## 测试（后端）

```powershell
cd backend
.\.venv\Scripts\activate
$env:APP_ENV = "development"
pytest tests/ -q
```

## Docker 部署（仅后端 API）

```powershell
cd backend
copy .env.example .env.production
docker compose -f deploy/docker-compose.yml up -d --build
```

MySQL / Ollama 仍在宿主机时，compose 已配置 `host.docker.internal`。

## 已实现 API

```http
POST /api/v1/auth/login
POST /api/v1/auth/switch-school
GET  /api/v1/auth/me
POST /api/v1/admin/users
GET  /api/v1/admin/users
```

`POST /api/v1/ask` 已接入多阶段 LangGraph（混合召回 + L1 + LLM + correct_sql）。
