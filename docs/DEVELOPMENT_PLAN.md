# 小奔智慧体育 · 智能问数（Data Copilot）开发大纲与计划

> **公司**：湖南小奔体育科技有限公司  
> **目标**：产品/运营/学校管理员用自然语言查 MySQL 数据，减少固定报表开发；第一期不上渠道商。  
> **技术路线**：**纯 Python** 问数服务 + **自研用户/权限表**（不依赖 `youplus-base-api`；**不修改** `youplus-base`、`sport-plantform`）  
> **运行环境**：**MySQL 5.7 在宿主机/公司库**；**RAGFlow 等中间件在 Docker**；本机先调试，配置区分 `development` / `production` 后上公司环境  
> **周期**：约 4 周（业余开发），按企业可观测、可审计、可降级标准交付 MVP  

---

## 0. 工程约束（必须遵守）

| 约束 | 说明 |
|------|------|
| **禁止改 Java 参考工程** | `youplus-base/`、`sport-plantform/` 仅作**业务表结构、报表口径、字段命名**参考，**不得提交任何修改** |
| **问数代码位置** | `backend/`（Python API）+ `frontend/`（Vue3）；根目录仅 `docs/` 与参考工程 |
| **身份与权限** | **自建** `copilot_sys_user` / `copilot_sys_user_school` 等表 + JWT；**不调用** `youplus-base-api` 的 `loginByAccount`、`centerLogin` 等 |
| **与体育后台关系** | 问数系统是**独立子产品**；账号不与现有体育后台打通（二期再评估 SSO） |
| **环境配置** | 后端 `backend/.env.*`、前端 `frontend/.env.*`；禁止写死在代码里 |
| **问数表命名** | 库名 `copilot`，表名统一 **`copilot_` 前缀**（如 `copilot_sys_user`），与业务库区分 |
| **中文注释（必须）** | 模块/类/公共函数写**中文** docstring；DDL 字段 `COMMENT`、权限/SQL 关键逻辑写行内注释；见 **§5.1** |

---

## 0.1 运行环境拓扑（本机开发 → 公司上线）

### 分工原则

| 部署位置 | 组件 | 说明 |
|----------|------|------|
| **宿主机 / 公司 DB 服务器** | **MySQL 5.7** | 公司业务库（只读账号）+ 问数库 `copilot`（用户/审计/指标） |
| **宿主机（本机开发）** | **Ollama** | 4070 跑本地大模型；问数服务通过 OpenAI 兼容 API 调用 |
| **宿主机（开发期）** | **Python 问数 API**、**Vue 前端 dev server** | 改代码热更新方便；上线可改为 Docker |
| **Docker Compose** | **RAGFlow 0.24 栈** +（可选）问数服务容器 | 文档 RAG、ES、Redis、MinIO 已与业务 MySQL **隔离** |

> **MySQL 不放进 Docker**：与公司现网一致，避免本机 Docker 与公司环境差异；问数只在 MySQL 上新增库 `copilot` 和只读账号。

### 本机 Docker 栈（已就绪）

当前 Compose 项目名一般为 `docker`，容器与端口如下（以你本机实际映射为准）：

| 容器名 | 镜像 | 宿主机端口 | 用途 |
|--------|------|------------|------|
| `ragflow-cpu-1` | `infiniflow/ragflow:v0.24.0` | **443** → 443 | RAGFlow Web / API（CPU 版；LLM 可指宿主机 Ollama） |
| `es01-1` | `elasticsearch:8.11.3` | **1200** → 9200 | RAGFlow 检索 / 向量与全文（问数二期可复用 ES API） |
| `redis-1` | `valkey:8` | **6379** | RAGFlow 缓存与任务队列 |
| `minio-1` | `minio` | **9000** | RAGFlow 文档对象存储 |

访问 RAGFlow：浏览器 `https://localhost` 或 `https://127.0.0.1`（视本地证书/端口为准）。

### 宿主机还需安装（问数开发）

| 工具 | 用途 | 备注 |
|------|------|------|
| **Python 3.11+** | FastAPI + LangGraph | 问数主服务 |
| **Node.js 18+** | Vue3 + Vite | 前端 |
| **Python venv** | **`backend/.venv/`** | 在 `backend/` 执行 `python -m venv .venv`，勿在仓库根建 venv |
| **Ollama** | 本地 LLM | `qwen2.5-coder:7b` 等；`LLM_API_BASE=http://127.0.0.1:11434/v1` |
| **MySQL 5.7 客户端** | 建库、迁移、调试 | 连公司业务库 + 建 `copilot` |
| **Git** | 版本管理 | |

**第一期不必单独再装**：Qdrant、PostgreSQL；字段/指标召回先用 **MySQL 表 + 术语 JSON**，需要时再对接 RAGFlow/ES。

### 整体拓扑图（本机）

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ 宿主机（Windows）                                                          │
│  · Ollama :11434          ← LLM（4070）                                   │
│  · MySQL 5.7 :3306        ← 业务库 + copilot 库                           │
│  · Python Uvicorn :8000   ← data-copilot-bot（开发期）                     │
│  · Vite :5173             ← 前端（开发期）                                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ host.docker.internal（容器访问宿主机）
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Docker Compose（RAGFlow 栈）                                               │
│  ragflow:443  │  elasticsearch:1200  │  redis:6379  │  minio:9000       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 配置分层（必须实现）

代码使用 `pydantic-settings`，通过 **`APP_ENV`** 加载不同 env 文件：

| 文件 | 场景 | 是否提交 Git |
|------|------|----------------|
| `backend/.env.example` | 后端变量模板 | ✅ 提交 |
| `backend/.env.development` | 本机 API 调试 | ❌ 不提交 |
| `backend/.env.production` | 公司 API | ❌ 不提交 |
| `frontend/.env.example` | 前端变量模板（`VITE_*`） | ✅ 提交 |
| `frontend/.env.development` | 本机 Vite | ❌ 不提交 |

加载顺序建议：`.env.{APP_ENV}` → 系统环境变量（生产用）。

```python
# 约定：backend/config/settings.py
# ROOT_DIR = backend/；加载 backend/.env.{APP_ENV}
```

### 本机 → 公司环境切换清单

上线公司时，仅需替换配置（同一份镜像/代码），重点改：

| 配置项 | 本机 `development` | 公司 `production` |
|--------|-------------------|-------------------|
| `MYSQL_BUSINESS_HOST` | `127.0.0.1` 或 VPN 地址 | 公司 MySQL 内网 IP |
| `MYSQL_COPILOT_HOST` | 同左（可与业务同实例） | 公司 MySQL 内网 IP |
| `LLM_API_BASE` | `http://127.0.0.1:11434/v1` | 内网 Ollama / 通义 / DeepSeek API |
| `JWT_SECRET` | 开发用随机串 | **强随机、仅生产一份** |
| `SEED_ADMIN_PASSWORD` | 简单密码 | **必须修改** |
| `RAGFLOW_BASE_URL` | `https://127.0.0.1` 或 `http://host.docker.internal:443` | 公司 RAGFlow 地址 |
| `ELASTICSEARCH_URL` | `http://127.0.0.1:1200` | 公司 ES 地址 |
| `APP_DEBUG` | `true` | `false` |
| `CORS_ORIGINS` | `http://localhost:5173` | 公司前端域名 |

---

## 1. 项目定位与边界

### 1.1 要做什么

| 能力 | 说明 |
|------|------|
| 自然语言问数 | 中文提问 → 生成 **只读 SELECT** → 表格结果 + 简短解读 |
| 角色与数据隔离 | 超管 / 运营 / 学校管理员看到的数据范围不同 |
| 企业可观测 | 每次提问可追溯：延迟、成功率、降级、badcase、审计 |
| 账号与权限 | 自研三类账户（超管 / 运营 / 学校），JWT 登录；学校账户可绑定多个 `sch_id` |
| 用户管理 | 仅**超管**可创建/禁用运营账户、学校账户；运营**不能**管理用户 |

### 1.2 第一期不做

- 渠道商、代理商（`QYDLYYRY22`、`YJDLS` 等）
- 复杂图表大屏、自助拖拽 BI
- 全库任意表问答（仅 **表白名单 + 15～20 条高频问法**）
- 写库、DDL、导出超大量数据
- 替换现有 `SportActivityNewReportController` 等固定报表接口

### 1.3 参考工程（只读，不修改）

| 路径 | 用途 |
|------|------|
| `sport-plantform/.../report/SportActivityNewReportController.java` | 业务报表口径、`sch_id` 过滤方式 |
| `sport-plantform/.../UserController.java`、`BaseController.java` | 对照现有系统「按校查数」习惯（**问数不复用其登录**） |
| `youplus-base/.../PeopleRoleType.java` | 仅作业务角色命名对照，问数侧用自研 `UserRole` 枚举 |

---

## 2. 角色与权限模型（第一期 · 自研账户）

### 2.1 三类账户（`UserRole` 枚举）

问数系统使用**独立账号体系**，与体育后台 `PeopleRoleType` **不一一打通**（命名可对齐理解）。

| 角色 | `role` 值 | 谁创建 | 用户管理 | 业务数据（问数 SQL） |
|------|-----------|--------|----------|----------------------|
| **超级管理员** | `ADMIN` | 系统首次启动**默认生成 1 个** | ✅ 创建/禁用运营、学校账户；改密 | **全部业务数据**，不强制 `sch_id` |
| **运营账户** | `OPERATOR` | 超管创建 | ❌ **不能**管理任何用户 | **全部业务数据**，不强制 `sch_id` |
| **学校账户** | `SCHOOL` | 超管创建 | ❌ 不能管理用户 | **仅已绑定**的 `sch_id` 范围内数据 |

**能力边界（必须写进代码）**：

| 能力 | ADMIN | OPERATOR | SCHOOL |
|------|:-----:|:--------:|:------:|
| 问数 | ✅ | ✅ | ✅ |
| 查全部业务库（白名单表） | ✅ | ✅ | ❌（仅绑定校） |
| 创建/禁用用户 | ✅ | ❌ | ❌ |
| 为学校账户绑定/解绑 `sch_id` | ✅ | ❌ | ❌ |
| 管理 badcase / 样例 SQL（一期可都给运营） | ✅ | ✅（可选） | ❌（可选） |

### 2.2 学校账户与多 `sch_id`

- 学校账户与学校是 **多对多**：`copilot_sys_user_school(user_id, sch_id)`。
- 超管在「用户管理」里为学校账户维护绑定列表（增删 `sch_id`）。
- **问数时的校上下文**：
  - JWT / 会话中带 `active_sch_id`（当前选中的学校）。
  - 若绑定多所：登录后前端展示校列表，调用 `POST /api/v1/auth/switch-school` 切换；**未选校不允许问数**。
  - SQL 策略：`sch_id = active_sch_id`（单校问数，与现有报表 `setSchId` 一致）；二期可加「跨绑定校汇总」→ `sch_id IN (...)`。
- **禁止**在 `/ask` body 里传 `schId` 作为权限依据；`active_sch_id` 只能来自服务端会话/JWT 声明（切换接口校验必须在绑定列表内）。

### 2.3 权限策略表（`PolicyService`）

```text
role == ADMIN      → 不注入 sch_id 条件（全平台业务数据，仍受表白名单约束）
role == OPERATOR   → 不注入 sch_id 条件（与超管相同的数据范围，无用户管理权）
role == SCHOOL     → REQUIRE sch_id = {active_sch_id}，且 active_sch_id ∈ user.bound_sch_ids
其它               → 403
```

**原则**：

- **永远不信任** LLM 或前端传的 `sch_id`；只信任 JWT 解析后的 `UserContext`。
- 学校账户：**服务端**在 SQL 执行前追加 `AND sch_id = ?`（字段名按表白名单配置）。
- 运营/超管：不追加 `sch_id`，但审计日志必须记录「全局查询」。

### 2.4 用户与权限表（简易实现）

库：与问数共用 **MySQL**（建议独立 schema：`copilot`），与业务库可同实例。

#### `copilot_sys_user`（账户）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT PK | |
| `username` | VARCHAR(64) UNIQUE | 登录名 |
| `password_hash` | VARCHAR(255) | bcrypt / argon2 |
| `display_name` | VARCHAR(128) | 显示名 |
| `role` | ENUM | `ADMIN` / `OPERATOR` / `SCHOOL` |
| `status` | TINYINT | 1 启用 0 禁用 |
| `created_by` | BIGINT NULL | 创建人（超管 id；系统种子账户为 NULL） |
| `created_at` / `updated_at` | DATETIME | |

#### `copilot_sys_user_school`（学校账户 ↔ 学校，仅 `role=SCHOOL` 使用）

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | BIGINT | FK → `copilot_sys_user.id` |
| `sch_id` | INT | 业务库学校 id |
| `sch_name` | VARCHAR(128) NULL | 冗余展示，可选 |
| PK | (`user_id`, `sch_id`) | |

#### 默认超管（启动种子）

应用**首次启动**或迁移时，若不存在任何 `ADMIN`，则根据环境变量创建：

```bash
SEED_ADMIN_USERNAME=admin
SEED_ADMIN_PASSWORD=change-me-on-deploy  # 生产必须改
```

> 种子脚本：`backend/scripts/seed_admin.py` 或 Alembic migration；密码不入库明文。

### 2.5 登录与身份传递（自研 JWT）

#### 2.5.1 登录

| 项 | 内容 |
|----|------|
| **接口** | `POST /api/v1/auth/login` |
| **请求** | `{ "username", "password" }` |
| **校验** | 查 `copilot_sys_user`；`status=1`；验证 `password_hash` |
| **响应** | `accessToken`（JWT）、`expiresIn`、`user`（id, username, role, boundSchools?） |

学校账户登录响应需带 `boundSchools: [{ schId, schName }]`；若仅 1 所，自动设 `active_sch_id`。

#### 2.5.2 后续请求

Header：**`Authorization: Bearer <JWT>`**（或兼容 `token: <JWT>`）。

JWT payload 建议：

```json
{
  "sub": "user_id",
  "role": "SCHOOL",
  "active_sch_id": 1140,
  "bound_sch_ids": [1140, 1220],
  "exp": 1735689600
}
```

- `OPERATOR` / `ADMIN`：无 `active_sch_id` / `bound_sch_ids`。
- `SCHOOL`：切换学校时签发新 token 或服务端会话更新 `active_sch_id`。

#### 2.5.3 超管 · 用户管理 API（仅 `ADMIN`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/admin/users` | 创建运营/学校账户 |
| GET | `/api/v1/admin/users` | 列表（分页） |
| PATCH | `/api/v1/admin/users/{id}` | 禁用/启用、重置密码 |
| PUT | `/api/v1/admin/users/{id}/schools` | 学校账户：覆盖绑定 `sch_id` 列表 |

创建运营账户示例：

```json
{ "username": "ops01", "password": "***", "role": "OPERATOR", "displayName": "运营张三" }
```

创建学校账户示例：

```json
{
  "username": "sch_xianghua",
  "password": "***",
  "role": "SCHOOL",
  "displayName": "桂花坪小学",
  "schIds": [1140, 1220]
}
```

#### 2.5.4 架构（无外部用户中心）

```text
浏览器 / 问数前端 (Vue)
        │ POST /api/v1/auth/login  → JWT
        │ POST /api/v1/ask         → Bearer JWT
        │ （超管）/api/v1/admin/users
        ▼
data-copilot-bot (Python FastAPI)
        │ AuthService：JWT 签发/校验
        │ UserRepository：copilot_sys_user / copilot_sys_user_school
        │ PolicyService → LangGraph → SQL 网关
        ├─► MySQL copilot schema（用户/审计/指标）
        └─► MySQL 业务库只读（智慧体育数据）
```

**`UserContext` 最小字段**：

```json
{
  "traceId": "uuid",
  "userId": 1,
  "username": "sch_xianghua",
  "role": "SCHOOL",
  "activeSchId": 1140,
  "boundSchIds": [1140, 1220],
  "clientIp": "10.x.x.x"
}
```

---

## 3. 系统架构

```text
┌─────────────────────────────────────────────────────────────────┐
│ 问数前端（Vue3，data-copilot-bot/frontend）                        │
│  · Vite dev :5173（本机） / Nginx 静态资源（公司）                  │
│  · POST /api/v1/auth/login  ·  /api/v1/ask  ·  /api/v1/admin/*   │
└────────────────────────────┬────────────────────────────────────┘
                             │ JWT + question
┌────────────────────────────▼────────────────────────────────────┐
│  data-copilot-bot（Python 3.11 + FastAPI，默认 :8000）              │
│  Auth(JWT) → LangGraph(Text2SQL) → PolicyService + sql_guard      │
│  Observability → MySQL copilot（copilot_ask_* / copilot_audit_log）               │
└──────┬──────────────────────────────┬───────────────────────────┘
       │                              │
       ▼                              ▼
 MySQL 5.7（宿主机/公司）          Ollama :11434（宿主机 LLM）
 · copilot 库                      或 公司 LLM API
 · 业务库只读

       │ （二期可选）RAG 文档 / 字段取值
       ▼
 Docker：RAGFlow + Elasticsearch:1200 + Redis:6379 + MinIO:9000
```

---

## 4. 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ | Agent / NL2SQL 生态 |
| Web | FastAPI + Uvicorn | 异步、OpenAPI |
| Agent | LangGraph + LangChain | 固定有向图，节点可 Trace |
| LLM | OpenAI 兼容 API | 通义 / DeepSeek / 私部署均可 |
| SQL 安全 | sqlglot + 自研规则 | 仅 SELECT、表白名单、强制 sch_id |
| DB 驱动 | SQLAlchemy / aiomysql | 连接池、超时 |
| 配置 | pydantic-settings + `.env` | 环境隔离 |
| 日志 | structlog 或 JSON logging | 每行带 `trace_id` |
| 认证 | **PyJWT** 或 **python-jose** + **passlib[bcrypt]** | 登录签发、密码哈希 |
| ORM / 迁移 | **SQLAlchemy 2** + **Alembic**（可选） | `copilot_sys_user` 等表 |
| 文档 RAG（已有） | **RAGFlow v0.24** + ES + MinIO + Valkey | Docker；问数 MVP 可不接 |
| 部署 | 本机进程 / **Docker Compose**（公司） | MySQL 始终在宿主机；问数服务可容器化 |
| 配置 | `.env.development` / `.env.production` | `APP_ENV` 切换 |

---

## 5. 仓库目录规划（`data-copilot-bot/`）

```text
data-copilot-bot/
├── docs/                            # 设计与规范（仓库级）
│   ├── DEVELOPMENT_PLAN.md
│   ├── ROLE_PERMISSION.md           # 待写
│   ├── TABLE_WHITELIST.md           # 待写
│   └── EVAL_QUESTIONS.md            # 待写
├── backend/                         # Python 问数 API
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                     # auth、admin_users、ask、health…
│   │   ├── core/                    # context、security
│   │   ├── auth/
│   │   ├── policy/
│   │   ├── agent/                   # LangGraph（待实现）
│   │   ├── db/
│   │   └── observability/
│   ├── config/settings.py
│   ├── scripts/                     # ddl_copilot.sql、seed_admin.py
│   ├── tests/
│   ├── deploy/docker-compose.yml
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── .env.example
│   ├── .env.development             # gitignore
│   └── .env.production              # gitignore
├── frontend/                        # Vue3 + Vite 问数前端
│   ├── src/
│   │   ├── api/                     # 封装 REST
│   │   ├── router/
│   │   ├── views/                   # login、ask、admin
│   │   └── utils/request.js
│   ├── package.json
│   ├── vite.config.js
│   ├── .env.example
│   └── .env.development             # gitignore
├── README.md
├── .gitignore
├── sport-plantform/                 # 参考，勿改
└── youplus-base/                    # 参考，勿改
```

### 5.1 代码注释规范（必须遵守）

问数为**企业可维护**交付，注释语言统一为**简体中文**（专有名词如 JWT、LangGraph 可保留英文）。

| 范围 | 要求 |
|------|------|
| **Python**（`backend/`） | 每个 `.py` 文件顶部模块说明；对外类/函数中文 docstring；`UserContext`、策略、SQL 网关、审计等写清业务含义 |
| **前端**（`frontend/src/`） | 工具类、路由守卫、API 封装、复杂组件 `<script>` 内用 `/** */` 或行内 `//` 中文说明 |
| **不必注释** | 显而易见的 getter、纯转发一行代码、自动生成代码 |
| **禁止** | 无意义注释（如 `// 循环`）；长期不更新的误导注释 |

示例（Python）：

```python
def require_school_scope(ctx: UserContext) -> int:
    """学校账户问数前校验：必须已选 active_sch_id 且在绑定校列表内。"""
    ...
```

进度跟踪见 [docs/PROGRESS.md](./PROGRESS.md)。

> **说明**：不修改 `sport-plantform` / `youplus-base`。若将来嵌入体育后台，用 **iframe 打开问数前端**，使用问数**自有 JWT**（不与体育 token 混用，除非二期做 SSO）。

---

## 6. LangGraph 流水线（固定 7 节点）

| 节点 | 职责 | 失败处理 |
|------|------|----------|
| `normalize_question` | 清洗、截断长度 | 记 `copilot_ask_span` |
| `retrieve_context` | 术语 + 表说明 + 相似样例 SQL | 无检索仍继续 |
| `match_curated` | 与预置问句相似度 | 命中 → **L1 降级**，跳过 LLM 生成 |
| `generate_sql` | LLM 生成 SQL | 超时 → 重试 1 次 → L2 |
| `validate_sql` | SELECT only、表白名单、禁多语句 | 失败 → L3 拒答 |
| `apply_policy` | 按角色注入 `sch_id`、LIMIT | 失败 → L3 |
| `execute_sql` | 只读库执行，超时 10s，max 5000 行 | timeout → 记指标 |
| `format_answer` | 表格 + 一句话总结 | 流式可选 |

**任务完成率**：`format_answer` 成功且 `execute_sql` 无异常 / 总请求。

---

## 7. 降级设计（L0～L3）

| 级别 | 名称 | 触发条件 | 行为 |
|------|------|----------|------|
| L0 | 正常 | 全流程成功 | LLM SQL |
| L1 | 样例命中 | 与 `EVAL_QUESTIONS` 相似度 ≥ 阈值 | 执行预置 SQL |
| L2 | 缩略生成 | LLM 超时或连续失败 | 更小模型 / 更短 prompt 再试一次 |
| L3 | 安全拒答 | 校验失败、越权、无法生成 | 固定文案 + 引导「标记 badcase」 |

**指标**：`degrade_level`、`degrade_rate = count(level>0)/count(*)`。

---

## 8. 可观测与审计（企业落地必选）

### 8.1 分析库表（`analytics` schema）

**`copilot_ask_session`**：会话级  
`session_id, user_id, role, active_sch_id, created_at`

**`copilot_ask_turn`**：每次提问一行  

| 字段 | 说明 |
|------|------|
| `trace_id` | 全链路 ID |
| `question` | 用户原问 |
| `final_sql` | 最终执行 SQL |
| `status` | success / fail / timeout / degraded |
| `degrade_level` | 0～3 |
| `retry_count` | 重试次数 |
| `error_code` | 枚举 |
| `latency_ms_total` | 总耗时 |
| `latency_ms_first_token` | 流式首包（可选） |
| `latency_ms_sql_gen` | 生成 SQL |
| `latency_ms_sql_exec` | 执行 SQL |
| `row_count` | 返回行数 |
| `token_in` / `token_out` | LLM 用量 |
| `user_feedback` | up / down / null |
| `is_badcase` | 0/1 |
| `human_corrected_sql` | 人工修正 |

**`copilot_ask_span`**：每节点一行  
`trace_id, node_name, started_at, duration_ms, status, detail_json`

**`copilot_audit_log`**：合规审计  
`trace_id, user_id, role, active_sch_id, question, sql_hash, tables_used, row_count, client_ip, created_at`

### 8.2 核心指标（周报 SQL / 后续 Grafana）

| 指标 | 计算 |
|------|------|
| 任务完成率 | `status=success / total` |
| 准确度（运营） | `user_feedback=up / 有反馈数` + 人工标注 |
| P95 / P99 延迟 | `percentile(latency_ms_total)` |
| 首 token 延迟 | `latency_ms_first_token` 分位 |
| 超时率 | `status=timeout / total` |
| 异常率 | `status=fail / total` |
| 重试率 | `retry_count > 0 / total` |
| 降级率 | `degrade_level > 0 / total` |

### 8.3 日志规范

每条日志 JSON 必含：`trace_id`, `user_id`, `role`, `active_sch_id`, `node`, `level`, `message`。

### 8.4 人工干预闭环

1. 运营在管理页对某 `trace_id` 标记 **badcase**。  
2. 填写 **正确 SQL** → 写入 `copilot_sql_example`（按 `role` + 场景分类）。  
3. 每周跑 `scripts/replay_eval.py` 回归评测集。

---

## 9. 数据与语义层（第一期）

### 9.1 MySQL 连接

- **部署**：MySQL **5.7 在宿主机/公司服务器**，不进 Docker。  
- **业务库**：只读账号，`max_execution_time` / 连接级 timeout；方言在 Prompt 中注明 **MySQL 5.7**（避免 8.0 专属语法）。  
- **问数库 `copilot`**：与业务可**同实例不同 database**；存 `copilot_sys_user`、`copilot_ask_*`、指标目录等；**表名统一前缀 `copilot_`**。  
- **本机**：`MYSQL_*_HOST=127.0.0.1`；问数服务在 Docker 内时用 `host.docker.internal`（Windows Docker Desktop）。

### 9.2 表白名单（待业务确认，示例方向）

与现有报表域对齐，优先活动/参与/stat 类表（参考 `SportActivityNewReportController` 所用 Service）：

| 域 | 可能表/视图 | 关键字段 |
|----|-------------|----------|
| 活动参与 | `sport_activity_*_stat*` | `activity_id`, `sch_id`, `stat_day` |
| 学校 | 学校维度表 | `sch_id`, `sch_name` |
| 打卡/完成 | `sport_activity_done_*` | `sch_id`, `student_id` |

> 详细表名在 `docs/TABLE_WHITELIST.md` 中维护（开发第 1 周完成）。

### 9.3 术语库（示例）

| 术语 | 定义 |
|------|------|
| 参与人数 | 周期内至少完成 1 次有效记录的去重学生数 |
| 本校 | 当前会话 `active_sch_id` 对应学校（学校账户） |
| 活动 | `activity_id` 指向的 `sport_activity_new` 配置 |

### 9.4 第一期评测问句（示例 5 条）

1. 本校本月跳绳活动参与人数是多少？  
2. 本校最近 7 天每日参与人数趋势？  
3. 指定活动 ID 下各班级参与人数排名（前 10）？  
4. 本校今日完成打卡的学生人数？  
5. （超管）昨日全平台活动参与人次汇总？  

完整列表目标 **15～20 条** → `docs/EVAL_QUESTIONS.md`。

---

## 10. API 约定（Python 服务）

### 10.1 `POST /api/v1/auth/login`

**请求**：

```json
{
  "username": "admin",
  "password": "***"
}
```

**响应**：

```json
{
  "accessToken": "eyJ...",
  "expiresIn": 86400,
  "user": {
    "id": 1,
    "username": "admin",
    "role": "ADMIN",
    "displayName": "系统管理员"
  }
}
```

学校账户额外返回 `boundSchools`；多所时前端引导选择或调 `switch-school`。

### 10.2 `POST /api/v1/auth/switch-school`（仅 `SCHOOL`）

**请求**：`{ "schId": 1140 }`（须在 `boundSchIds` 内）  
**响应**：新 `accessToken`（更新 `active_sch_id`）。

### 10.3 超管用户管理（仅 `ADMIN`）

见 §2.5.3；所有接口需 `Authorization: Bearer` 且 `role=ADMIN`。

### 10.4 `POST /api/v1/ask`

**请求 Header**：`Authorization: Bearer <JWT>`  

**请求 Body**（**不含** `schId` / `role`，防篡改）：

```json
{
  "traceId": "optional-uuid",
  "sessionId": "optional",
  "question": "本校本月跳绳参与人数",
  "options": {
    "stream": false
  }
}
```

服务端流程：校验 JWT → 加载 `copilot_sys_user`（及绑定校）→ `UserContext` → `PolicyService` → LangGraph。

**响应**：

```json
{
  "traceId": "uuid",
  "status": "success",
  "degradeLevel": 0,
  "sql": "SELECT ...",
  "columns": ["cnt"],
  "rows": [[123]],
  "answer": "本校本月跳绳参与人数为 123 人。",
  "latencyMs": 3200
}
```

### 10.5 `POST /api/v1/feedback`

```json
{
  "traceId": "uuid",
  "feedback": "down",
  "isBadcase": true,
  "correctedSql": "SELECT ..."
}
```

### 10.6 健康检查

`GET /health`、`GET /ready`（MySQL `copilot` + 业务只读库连通）。

---

## 11. 认证与用户管理任务清单

| 任务 | 说明 |
|------|------|
| `ddl_copilot.sql` | 全部 `copilot_*` 表，字段带 COMMENT |
| `seed_admin` | 无 ADMIN 时按环境变量创建默认超管 |
| `POST /auth/login` | bcrypt 校验 + 签发 JWT |
| `get_current_user` | FastAPI Depends；解析 JWT → `UserContext` |
| `POST /auth/switch-school` | 校验绑定关系后刷新 token |
| `admin/users` CRUD | 仅 ADMIN；运营不能访问 |
| `PUT .../schools` | 维护学校账户的 `sch_id` 列表 |
| `role_policy` | ADMIN/OPERATOR 不注入 sch；SCHOOL 强制 `active_sch_id` |
| 单元测试 | 运营调 admin API → 403；学校查别校 → SQL 网关拒绝 |

---

## 12. 四周开发计划

### 第 1 周：地基 + 可观测

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | 初始化 `backend/` + `frontend/`：FastAPI、Vite、Docker | 前后端可启动 |
| 2～3 | `ddl_analytics.sql` 建表；`tracer` 写 `copilot_ask_turn/copilot_ask_span/copilot_audit_log` | 打一条假请求有记录 |
| 2～3 | `ddl_copilot.sql` + `copilot_sys_user` + `seed_admin` | 默认超管可登录 |
| 3～4 | JWT 登录 + `role_policy` 单测 | ADMIN/OPERATOR/SCHOOL 策略通过 |
| 4～5 | MySQL 业务只读 + 硬编码 SQL | `/ask` 假用户返回结果 |
| 5～7 | `/admin/users` 创建运营/校账户 + `/ask` JWT | Postman 端到端 |

**周验收**：超管登录 → 创建学校账户并绑定 `sch_id` → 该校账户仅能查绑定校；审计表有记录。

---

### 第 2 周：SQL 安全 + LangGraph

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | `sql_guard`：SELECT only、表白名单、LIMIT | `test_sql_guard` 通过 |
| 2～3 | `sch_id` 强制注入（仅 `SCHOOL`） | **串校回归测试** 5 用例 |
| 3～5 | LangGraph 7 节点打通 + LLM 配置 | 真实问句出 SQL |
| 5～7 | L1 样例降级 + 术语/样例 JSON | 评测问句命中样例 |

**周验收**：校管无法查他校；指标表有 `latency_*`、`status`。

---

### 第 3 周：RAG + 前端 + 降级

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | 表/字段 metadata + 检索 | `TABLE_WHITELIST.md` |
| 2～3 | L2/L3 降级与重试 | `degrade_level` 正确 |
| 3～5 | 极简前端：登录 + 问数 + 超管用户管理页 | 内网可演示 |
| 5～7 | `feedback` API + badcase 标记 | 人工修正 SQL 入库 |

**周验收**：运营/校管各 2 人试用；能标记 badcase。

---

### 第 4 周：评测 + 试点 + 文档

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | `EVAL_QUESTIONS` 15～20 条 + `replay_eval.py` | 完成率基线报告 |
| 2～3 | 限流、请求大小限制、错误码统一 | 防刷 |
| 3～4 | 周报 SQL：P95、降级率、异常率 | `docs/WEEKLY_METRICS.md` 模板 |
| 4～5 | 部署文档、`.env.example` | 同事可复现 |
| 5～7 | 修 Top5 badcase；写 Phase2  backlog | **MVP 演示** |

**月验收标准**：

- [ ] 三类账户可用；运营**无法**进用户管理；学校账户**零串校**（自动化覆盖）  
- [ ] 每次提问可查 `trace_id`、审计、span  
- [ ] 15 条评测问句完成率 ≥ 70%（可调整）  
- [ ] 有 badcase → 样例 SQL 闭环  

---

## 13. 风险与对策

| 风险 | 对策 |
|------|------|
| 业余时间不足 | 严格砍功能；L1 样例覆盖高频问 |
| LLM 成本高 | 限流、每日配额、L1 优先 |
| 表结构复杂 | 白名单仅 5～8 张表；视图封装 |
| 学校账户未选校 | `active_sch_id` 为空 → 400，引导 `switch-school` |
| 默认超管密码泄露 | 生产必须改 `SEED_ADMIN_PASSWORD`；首次登录强制改密（二期） |
| 与体育后台账号两套 | 文档写清；避免用户混淆；二期再评估 SSO |
| SQL 注入 | sqlglot 解析 + 参数化 sch_id + 只读账号 |
| Docker 访问本机 MySQL 失败 | 使用 `host.docker.internal`；Linux 生产可改用宿主机 IP |
| RAGFlow 与 Ollama 抢 GPU | RAGFlow 用 CPU 版；LLM 走宿主机 Ollama；embedding 高峰勿与 14B 同时满载 |

---

## 14. Phase 2  backlog（一个月后）

- 对接 `youplus-base-api` / 体育后台 SSO（单点登录）  
- 学校账户：跨绑定校汇总问数（`sch_id IN (...)`）  
- 渠道商租户模型  
- 流式输出 + 首 token 指标  
- Langfuse / OpenTelemetry 接入  
- 图表（AntV）  
- 与 `SportActivityNewReportController` 部分报表「问数替代」评估  

---

## 15. 环境变量与配置文件

### 15.1 文件约定

| 文件 | 说明 |
|------|------|
| `backend/.env.example` | 后端模板，**提交 Git** |
| `backend/.env.development` | 本机 API，**不提交** |
| `backend/.env.production` | 公司 API，**不提交** |
| `frontend/.env.example` | 前端模板（`VITE_API_BASE`），**提交 Git** |
| `frontend/.env.development` | 本机 Vite，**不提交** |

后端启动前：`cd backend` 并设置 `APP_ENV=development` 或 `production`。

### 15.2 `backend/.env.example`（全量变量模板）

```bash
# ---------- 运行环境 ----------
APP_ENV=development
APP_DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000
# 前端 dev 代理或生产域名，逗号分隔
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# ---------- LLM（OpenAI 兼容）----------
# 本机 Ollama：
LLM_API_BASE=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5-coder:7b
LLM_TIMEOUT_SEC=120

# ---------- MySQL 5.7（宿主机/公司，非 Docker）----------
# 业务库（只读）
MYSQL_BUSINESS_HOST=127.0.0.1
MYSQL_BUSINESS_PORT=3306
MYSQL_BUSINESS_USER=ask_readonly
MYSQL_BUSINESS_PASSWORD=
MYSQL_BUSINESS_DATABASE=sport

# 问数库（读写：用户/审计/指标）
MYSQL_COPILOT_HOST=127.0.0.1
MYSQL_COPILOT_PORT=3306
MYSQL_COPILOT_USER=copilot
MYSQL_COPILOT_PASSWORD=
MYSQL_COPILOT_DATABASE=copilot

# ---------- JWT / 超管种子 ----------
JWT_SECRET=change-me-use-long-random-string-min-32-chars
JWT_EXPIRE_HOURS=24
SEED_ADMIN_USERNAME=admin
SEED_ADMIN_PASSWORD=change-me-on-deploy

# ---------- SQL 安全 ----------
SQL_DIALECT=mysql
SQL_MAX_ROWS=5000
SQL_TIMEOUT_SEC=10
ASK_RATE_LIMIT_PER_USER_PER_MIN=20

# ---------- RAGFlow 栈（Docker，二期对接可选）----------
RAGFLOW_ENABLED=false
RAGFLOW_BASE_URL=https://127.0.0.1
# RAGFlow 内配置 Ollama 时填：http://host.docker.internal:11434
ELASTICSEARCH_URL=http://127.0.0.1:1200
REDIS_URL=redis://127.0.0.1:6379/0
MINIO_ENDPOINT=http://127.0.0.1:9000
```

### 15.3 本机 `development` 要点

```bash
APP_ENV=development
APP_DEBUG=true
LLM_API_BASE=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5-coder:7b
MYSQL_BUSINESS_HOST=127.0.0.1
MYSQL_COPILOT_HOST=127.0.0.1
RAGFLOW_ENABLED=false
ELASTICSEARCH_URL=http://127.0.0.1:1200
```

前端 `vite.config.ts` 将 `/api` 代理到 `http://127.0.0.1:8000`。

### 15.4 公司 `production` 要点

```bash
APP_ENV=production
APP_DEBUG=false
# 示例：内网 LLM 或云端
# LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
# LLM_API_KEY=sk-xxx
# LLM_MODEL=qwen-plus

MYSQL_BUSINESS_HOST=10.x.x.x
MYSQL_COPILOT_HOST=10.x.x.x
JWT_SECRET=<生产环境独立强密钥>
SEED_ADMIN_PASSWORD=<部署后首次登录即改>
CORS_ORIGINS=https://ask.xiaoben.internal
RAGFLOW_BASE_URL=https://ragflow.xiaoben.internal
```

问数服务若用 Docker 部署在公司机：`MYSQL_*_HOST` 填 MySQL 服务器 IP，**不要**填 `127.0.0.1`（除非 MySQL 与容器同机且用 host 网络）。

### 15.5 RAGFlow 与 Ollama 联调说明

1. 在 RAGFlow 控制台添加模型供应商：**OpenAI-API-Compatible**。  
2. Base URL：`http://host.docker.internal:11434/v1`（容器访问宿主机 Ollama）。  
3. Embedding 可在 RAGFlow 内选 `bge-m3` 等（走 Ollama 或内置），与问数 **copilot 库无关**。  
4. 问数 MVP 的 Text2SQL **直接调 Ollama**，不依赖 RAGFlow 也能跑通。

---

## 16. 部署清单速查

| 组件 | 本机 | 公司 |
|------|------|------|
| MySQL 5.7 | 已安装，建 `copilot` + 只读账号 | 同左，用内网地址 |
| RAGFlow + ES + Redis + MinIO | Docker 已运行 | Docker 或运维统一部署 |
| Ollama + 模型 | 宿主机安装 | 内网 GPU 机或改云端 API |
| 问数 API | `uvicorn` 宿主机 :8000 | Docker / systemd |
| 问数前端 | `npm run dev` :5173 | Nginx 静态 + 反代 API |

---

## 17. 相关代码索引（仅业务参考，禁止修改）

| 说明 | 位置 |
|------|------|
| 校维度报表示例 | `sport-plantform/.../SportActivityNewReportController` → `setSchId(getUser().getSchId())` |
| 旧系统角色命名对照 | `youplus-base/.../PeopleRoleType.java`（问数用 `ADMIN`/`OPERATOR`/`SCHOOL`） |
| 体育后台登录（不集成） | `sport-plantform/.../UserController#login` |

问数侧用户体系以本文 **§2.4** `copilot_sys_user` / `copilot_sys_user_school` 为准。

---

**文档版本**：v1.6  
**变更**：问数表统一 `copilot_` 前缀，DDL 字段 COMMENT；开发进度见 [PROGRESS.md](./PROGRESS.md)。  
**维护**：随表白名单、评测集、公司 IP 更新同步改第 9、12、15 节；每完成里程碑更新 PROGRESS。

---

## 18. 工程脚手架（已落地）

| 路径 | 说明 |
|------|------|
| [backend/.env.example](../backend/.env.example) | 后端环境变量模板 |
| [backend/config/settings.py](../backend/config/settings.py) | `APP_ENV` → `backend/.env.{env}` |
| [backend/app/main.py](../backend/app/main.py) | FastAPI + CORS + 认证路由 |
| [backend/scripts/ddl_copilot.sql](../backend/scripts/ddl_copilot.sql) | copilot 库 DDL（`copilot_*` 表 + 字段 COMMENT） |
| [backend/scripts/migrate_tables_to_copilot_prefix.sql](../backend/scripts/migrate_tables_to_copilot_prefix.sql) | 旧表名一次性 RENAME（可选） |
| [backend/scripts/seed_admin.py](../backend/scripts/seed_admin.py) | 默认超管种子 |
| [backend/deploy/docker-compose.yml](../backend/deploy/docker-compose.yml) | API 容器部署 |
| [frontend/](../frontend/) | Vue3 + Vite 骨架（登录、路由、Axios） |
| [README.md](../README.md) | 前后端启动步骤 |
| [docs/PROGRESS.md](./PROGRESS.md) | 开发进度与里程碑 |
