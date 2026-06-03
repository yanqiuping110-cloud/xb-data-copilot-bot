# 小奔智慧体育 · 智能问数（Data Copilot）开发大纲与计划

> **公司**：湖南小奔体育科技有限公司  
> **目标**：产品/运营/学校管理员用自然语言查 MySQL 数据，减少固定报表开发；第一期不上渠道商。  
> **技术路线**：**纯 Python** 问数服务 + **自研用户/权限表**（不依赖 `youplus-base-api`；**不修改** `youplus-base`、`sport-plantform`）  
> **运行环境**：**MySQL 5.7 在宿主机/公司库**；**Elasticsearch + Embedding 在 Docker/宿主机**；本机先调试，配置区分 `development` / `production` 后上公司环境  
> **周期**：约 **6 周**（业余开发）：前 2 周地基与 LangGraph 基线已完成；**第 3～6 周**聚焦元数据知识库、语义库、混合召回与多阶段推理；按企业可观测、可审计、可降级标准交付 MVP  
> **问数核心路线**：**元数据知识库 + 语义库（前端可配置）→ 向量 + 全文混合召回 → 多阶段 LangGraph 推理 → LLM 生成 SQL**（L1 样例仅作高频快路径，不追求全覆盖）

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

**检索栈（第 3 周起）**：结构化元数据存 **copilot MySQL**；字段/指标 **向量索引** 走 **Elasticsearch dense_vector**（复用 Docker `:1200`）或独立 Qdrant（二选一，默认 ES）；字段取值 **全文检索** 走 **Elasticsearch**；Embedding 走 **Ollama 兼容 API**（与 LLM 可同 base）。RAGFlow 文档 RAG 与问数元数据**解耦**，问数不依赖 RAGFlow 控制台。

### 整体拓扑图（本机）

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ 宿主机（Windows）                                                          │
│  · Ollama :11434          ← LLM（4070）                                   │
│  · MySQL 5.7 :3306        ← 业务库 + copilot 库                           │
│  · Python Uvicorn :8000   ← data-copilot-bot（开发期）                     │
│  · Vite :5173             ← 前端（开发期，含元数据/语义库管理页）            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ host.docker.internal（容器访问宿主机）
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Docker / 检索服务                                                          │
│  elasticsearch:1200  ← 问数字段向量 + 字段取值全文（第 3 周接入）            │
│  （可选）ragflow:443 / redis / minio — 文档 RAG，与问数元数据解耦           │
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
| 自然语言问数 | 中文提问 → **混合召回上下文** → 多阶段推理 → 只读 SELECT → 表格 + 解读 |
| 元数据知识库 | 业务表/字段/表关系结构化存储；支持从 `information_schema` 半自动同步 + **前端人工维护** |
| 语义库 | 指标口径、别名、与字段/表的关联；**前端可配置**，驱动 LLM Prompt 与召回 |
| 混合召回 | 问句 → 字段/指标 **向量召回** + 字段取值 **全文召回** + MySQL 结构化补全 |
| 角色与数据隔离 | 超管 / 运营 / 学校管理员看到的数据范围不同 |
| 企业可观测 | 每次提问可追溯：延迟、成功率、降级、badcase、审计 |
| 账号与权限 | 自研三类账户（超管 / 运营 / 学校），JWT 登录；学校账户可绑定多个 `sch_id` |
| 用户管理 | 仅**超管**可创建/禁用运营账户、学校账户；运营**不能**管理用户 |

### 1.2 第一期不做

- 渠道商、代理商（`QYDLYYRY22`、`YJDLS` 等）
- 复杂图表大屏、自助拖拽 BI
- 全库任意表问答（仅 **表白名单 5～15 张表** + 元数据覆盖范围内问答）
- 仅靠无限堆叠 L1 SQL 样例覆盖全部业务（L1 只保留 **Top 高频 20～30 条**）
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
| 管理 badcase / 样例 SQL | ✅ | ✅（可选） | ❌（可选） |
| **元数据知识库**（表/字段/关系） | ✅ | ✅ | ❌ |
| **语义库**（指标/字段取值/别名） | ✅ | ✅ | ❌ |
| **触发索引重建**（同步 ES 向量/全文） | ✅ | ✅ | ❌ |

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
│  · 问数对话页  · 超管用户管理  · **元数据/语义库管理**（ADMIN/OPERATOR）│
│  · POST /api/v1/auth/login  ·  /api/v1/ask  ·  /api/v1/admin/*   │
└────────────────────────────┬────────────────────────────────────┘
                             │ JWT + question
┌────────────────────────────▼────────────────────────────────────┐
│  data-copilot-bot（Python 3.11 + FastAPI，默认 :8000）              │
│  Auth(JWT) → LangGraph（多阶段推理 + Text2SQL）→ Policy + sql_guard │
│  MetaKnowledgeService：MySQL 元数据 ↔ ES 向量/全文索引              │
│  Observability → MySQL copilot（copilot_ask_* / copilot_audit_log） │
└──────┬──────────────────────────────┬───────────────────────────┘
       │                              │
       ▼                              ▼
 MySQL 5.7（宿主机/公司）          Ollama :11434（LLM + Embedding）
 · copilot 库：用户/审计/元数据/语义
 · 业务库只读

       │
       ▼
 Elasticsearch :1200（Docker）
 · 字段/指标向量索引（dense_vector）
 · 字段取值全文索引（keyword/text）
```

---

## 4. 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ | Agent / NL2SQL 生态 |
| Web | FastAPI + Uvicorn | 异步、OpenAPI |
| Agent | LangGraph + LangChain | **多阶段有向图**：召回 → 合并过滤 → 生成 → 校验 → 执行 |
| LLM | OpenAI 兼容 API | 通义 / DeepSeek / Ollama 等 |
| Embedding | OpenAI 兼容 API | 与 LLM 可同 Ollama base；字段/指标/问句向量化 |
| 向量检索 | **Elasticsearch dense_vector**（默认） | 复用 Docker ES `:1200`；可选 Qdrant |
| 全文检索 | **Elasticsearch** | 字段取值、枚举、校名/项目名等 |
| 元数据存储 | **MySQL copilot_*** | 表/字段/关系/指标/取值权威数据源 |
| SQL 安全 | sqlglot + 自研规则 | 仅 SELECT、表白名单、强制 sch_id |
| DB 驱动 | SQLAlchemy / aiomysql | 连接池、超时 |
| 配置 | pydantic-settings + `.env` | 环境隔离 |
| 日志 | structlog 或 JSON logging | 每行带 `trace_id` |
| 认证 | **PyJWT** 或 **python-jose** + **passlib[bcrypt]** | 登录签发、密码哈希 |
| ORM / 迁移 | **SQLAlchemy 2** + **Alembic**（可选） | `copilot_sys_user` 等表 |
| 文档 RAG（可选） | **RAGFlow v0.24** + MinIO + Valkey | 与问数元数据**解耦**；问数检索直连 ES |
| 部署 | 本机进程 / **Docker Compose**（公司） | MySQL 始终在宿主机；问数服务可容器化 |
| 配置 | `.env.development` / `.env.production` | `APP_ENV` 切换 |

---

## 5. 仓库目录规划（`data-copilot-bot/`）

```text
data-copilot-bot/
├── docs/                            # 设计与规范（仓库级）
│   ├── DEVELOPMENT_PLAN.md
│   ├── ROLE_PERMISSION.md           # 待写
│   ├── TABLE_WHITELIST.md           # 初始表白名单参考（逐步迁入 copilot_table_meta）
│   ├── META_KNOWLEDGE.md            # 元数据/语义库字段说明与维护规范
│   └── EVAL_QUESTIONS.md            # 待写
├── backend/                         # Python 问数 API
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                     # auth、admin_users、ask、admin_meta…
│   │   ├── core/                    # context、security
│   │   ├── auth/
│   │   ├── policy/
│   │   ├── agent/                   # LangGraph 多阶段节点
│   │   ├── meta/                    # 元数据/语义库 Repository + 索引构建
│   │   ├── retrieval/               # 混合召回（向量 + 全文 + MySQL 补全）
│   │   ├── db/
│   │   └── observability/
│   ├── config/settings.py
│   ├── scripts/                     # ddl、seed、sync_table_meta、build_search_index
│   ├── tests/
│   ├── deploy/docker-compose.yml
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── .env.example
│   ├── .env.development             # gitignore
│   └── .env.production              # gitignore
├── frontend/                        # Vue3 + Vite 问数前端
│   ├── src/
│   │   ├── api/                     # 封装 REST（含 adminMeta.js）
│   │   ├── router/
│   │   ├── views/                   # login、ask、admin、AdminMetaTables…
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

## 6. LangGraph 流水线（多阶段推理 + L1 快路径）

> 对标电商问数「检索 → 过滤 → 生成 → 校验 → 执行」；在保留企业 **L1 样例快路径** 与 **sch_id 策略** 的前提下扩展节点。  
> **第 2 周基线**（7 节点）已实现；**第 5 周**将 `retrieve_context` 拆分为下列召回/合并子阶段。

### 6.1 目标流水线（第 5 周完整版）

| 阶段 | 节点 | 职责 | 失败处理 |
|------|------|------|----------|
| 预处理 | `normalize_question` | 清洗、截断长度 | 记 `copilot_ask_span` |
| 召回 | `extract_keywords` | LLM/规则抽取问句关键词 | 降级为整句检索 |
| 召回 | `recall_columns` | 字段向量召回（ES） | 空结果仍继续 |
| 召回 | `recall_metrics` | 指标向量召回（ES） | 空结果仍继续 |
| 召回 | `recall_field_values` | 字段取值全文召回（ES） | 空结果仍继续 |
| 合并 | `merge_retrieved_info` | 合并三路召回 + MySQL 补全表/关系 | 记 span detail |
| 过滤 | `filter_tables` | 按召回得分筛候选表（Top-N） | |
| 过滤 | `filter_metrics` | 筛候选指标与口径 | |
| 上下文 | `build_llm_context` | 拼表说明、JOIN 提示、指标公式、取值映射 | 无检索仍用白名单兜底 |
| 快路径 | `match_curated` | L1 样例命中则 **跳过 LLM 生成** | 命中 → `degrade_level=1` |
| 生成 | `generate_sql` | LLM 生成 SQL | 超时/失败 → L2 精简重试 1 次 |
| 校验 | `validate_sql` | SELECT only、表白名单、LIMIT | 失败 → 可选 `correct_sql` 1 次 → L3 |
| 策略 | `apply_policy` | 按角色注入 `sch_id`、LIMIT | 失败 → L3 |
| 执行 | `execute_sql` | 只读库执行，超时 10s，max 5000 行 | timeout → 记指标 |
| 回答 | `format_answer` | 表格 + 一句话总结 | 流式可选（Phase 2） |

**路由要点**：

- `match_curated` 在 `build_llm_context` 之后：L1 命中则直接进入 `validate_sql`。
- `validate_sql` 失败且 `retry_count < 1` 时走 `correct_sql`（带错误信息重生成），仍失败则 L3 拒答。

### 6.2 当前已落地（第 2 周基线，待演进）

| 节点 | 现状 | 演进方向 |
|------|------|----------|
| `retrieve_context` | 全量指标 + 关键词 Top-K 样例 | 拆为 §6.1 召回/合并/过滤链 |
| `match_curated` | L1 + MVP | 保留；样例来源含前端维护的 `copilot_sql_example` |
| `generate_sql` | 单次 LLM + L2 重试 | 接入 `build_llm_context` 结构化 Prompt |
| 其余节点 | 已实现 | 增加 `correct_sql`（第 5 周） |

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
2. 优先补 **元数据/指标/字段取值**；必要时填写 **正确 SQL** → 写入 `copilot_sql_example`。  
3. 触发 **索引重建**（若改了 alias/取值）。  
4. 每周跑 `scripts/replay_eval.py` 回归评测集。

---

## 9. 元数据知识库与语义库

> **原则**：MySQL `copilot_*` 为**权威数据源**（前端可 CRUD）；Elasticsearch 为**检索索引**（由后端脚本/管理页触发重建）；业务库 `information_schema` 仅用于**只读拉取**表/字段备注与类型，**不反向写入业务库**。  
> **表/字段「有效定义」**：自动读取业务库 COMMENT 为底稿；运营可在前端**人工补充/覆盖**；**人工非空时优先级高于自动备注**（见 §9.2.5）。  
> 参考 [shopkeeper-agent](https://github.com/didilili/shopkeeper-agent) 的 `table_info` / `column_info` / `metric_info` 分层，并增加 **表关系**、**字段取值**、**前端管理** 等企业字段。

### 9.1 MySQL 连接（不变）

- **部署**：MySQL **5.7 在宿主机/公司服务器**，不进 Docker。  
- **业务库**：只读账号；方言 Prompt 注明 **MySQL 5.7**。  
- **问数库 `copilot`**：用户/审计/**元数据/语义**；表名统一 **`copilot_` 前缀**。  
- **Elasticsearch**：Docker `:1200`；索引名前缀 `copilot_ask_`（与 RAGFlow 索引隔离）。

### 9.2 元数据知识库（结构层 · MySQL）

#### 9.2.1 表清单

| 表名 | 说明 | 前端管理 |
|------|------|----------|
| `copilot_table_meta` | 业务表注册：表名、fact/dim、业务域、粒度、sch_id 字段 | ✅ 表管理页 |
| `copilot_column_meta` | 字段：类型、角色(pk/fk/measure/dim/time)、描述、别名 | ✅ 字段管理页（按表） |
| `copilot_table_relation` | 表间 JOIN：from/to 列、关系类型、JOIN 提示 | ✅ 关系管理页 |
| `copilot_field_value` | 字段枚举/取值：value、展示名、别名（如 project_id=1→跳绳） | ✅ 取值管理页 |

#### 9.2.2 `copilot_table_meta` 核心字段（DDL 见 `V004__meta_knowledge.sql`）

| 字段 | 说明 |
|------|------|
| `table_name` | 业务表名，问数白名单权威来源 |
| `table_role` | `fact` / `dim` / `bridge` |
| `biz_domain` | 活动参与 / 打卡 / 学校 等 |
| `table_comment_auto` | **自动**：从业务库 `information_schema.TABLES.TABLE_COMMENT` 读取 |
| `description_manual` | **人工**：运营填写的表业务定义；**非空时覆盖** `table_comment_auto` |
| `grain` | 数据粒度说明（通常人工填写） |
| `sch_id_column` | 学校隔离字段，默认 `sch_id` |
| `last_introspected_at` | 最近一次从业务库拉取结构的时间 |
| `status` | 1 启用（可问数）0 停用 |

**有效表描述（问数/Prompt/索引用）**：

```text
effective_table_description =
  TRIM(description_manual) 非空 ? description_manual : table_comment_auto
```

#### 9.2.3 `copilot_column_meta` 核心字段

| 字段 | 说明 |
|------|------|
| `column_name` | 字段名 |
| `data_type` | **自动**：业务库 `COLUMN_TYPE`（如 `bigint(20)`），同步时更新 |
| `column_comment_auto` | **自动**：业务库 `COLUMN_COMMENT` |
| `description_manual` | **人工**：运营补充的业务定义；**非空时覆盖** `column_comment_auto` |
| `column_role` | `pk` / `fk` / `measure` / `dimension` / `filter` / `time`（人工维护） |
| `alias_json` | 别名数组（人工维护） |
| `sample_values_json` | 示例值（人工或后续采样脚本） |
| `is_nullable` | **自动**：来自 `information_schema` |

**有效字段描述**：

```text
effective_column_description =
  TRIM(description_manual) 非空 ? description_manual : column_comment_auto
```

#### 9.2.4 构建流程（后端脚本 + 前端触发）

```text
① 前端输入表名 → GET /admin/meta/introspect/tables/{tableName}
   只读 business information_schema：表 COMMENT + 各字段 COLUMN_TYPE / COLUMN_COMMENT
   （不落库，供运营预览）

② 运营在预览页补充 description_manual、grain、column_role、alias 等 → 保存
   POST /admin/meta/tables 或 PUT /admin/meta/tables/{id}
   POST /admin/meta/tables/{id}/columns（批量）

③ 后续「刷新结构」→ POST /admin/meta/tables/{id}/refresh-from-business
   仅更新 data_type、column_comment_auto、table_comment_auto、is_nullable
   **绝不覆盖** 已有非空 description_manual / alias_json / column_role

④ scripts/sync_table_meta_from_business.py（CLI 批量，规则同③）

⑤ POST /api/v1/admin/meta/rebuild-index → ES 向量/全文（用 effective_* 描述）

⑥ /ask 问数时 HybridRetriever 读 ES + MySQL 补全 JOIN
```

#### 9.2.5 自动读取 vs 人工定义（优先级规则）

| 场景 | 行为 |
|------|------|
| 首次录入表名 | 拉取业务库备注/类型 → 写入 `*_auto` 字段；人工列可留空 |
| 运营填写 `description_manual` | 问数 Prompt、混合召回、索引文本均用 **人工定义** |
| 运营清空 `description_manual` | 回退为 `*_auto`（业务库 COMMENT） |
| 业务库 COMMENT 变更后点「刷新结构」 | 更新 `*_auto`；**不改动** 非空 `description_manual` |
| 业务库新增字段 | 刷新后追加新字段行（仅 auto）；已有字段保留人工内容 |
| 业务库删除字段 | 刷新标记 `column_meta.status=0` 或逻辑删除，不物理删（保留审计） |

**前端展示约定**：

- 两列对照：**业务库备注（只读）** | **问数定义（可编辑，优先生效）**
- 有效定义列灰字预览：`effective = 人工 ?? 自动`
- 字段列表必显：`column_name`、`data_type`、业务库备注、问数定义、有效定义

**初始表白名单**（与现有种子对齐，逐步迁入 `copilot_table_meta`）：

| 域 | 优先表 | 关键字段 |
|----|--------|----------|
| 活动打卡 | `sport_activity_qzs_record` | `people_id`, `sch_id`, `project_id`, `create_time` |
| 活动参与 stat | `sport_activity_*_stat*` | `activity_id`, `sch_id`, `stat_day` |
| 学校 | 学校维度表 | `sch_id`, `sch_name` |
| 打卡/完成 | `sport_activity_done_*` | `sch_id`, `student_id` |

### 9.3 语义库（口径层 · MySQL）

在现有表上扩展，并增加指标-字段关联：

| 表名 | 说明 | 前端管理 |
|------|------|----------|
| `copilot_metric_definition` | 指标：名称、口径、公式、时间字段、别名（**已有，扩展字段**） | ✅ 指标管理页 |
| `copilot_metric_column` | 指标 ↔ 字段 多对多（measure/filter/group_by/join_key） | ✅ 指标详情内关联 |
| `copilot_sql_example` | L1 样例 SQL（**已有**）；可由 badcase 闭环或前端录入 | ✅ 样例管理页 |

#### 9.3.1 `copilot_metric_definition` 扩展字段（V004）

| 字段 | 说明 |
|------|------|
| `formula_text` | 口径公式，如 `COUNT(DISTINCT people_id)` |
| `filter_hint` | 默认过滤条件说明 |
| `time_column` | 默认时间字段 |
| `agg_type` | `count_distinct` / `sum` / `rate` 等 |
| `unit` | 人 / 次 / % |
| `admin_only` | 是否仅超管/运营可查 |
| `sql_template` | 参考 SQL 片段（非 L1 全句，供 Prompt few-shot） |

#### 9.3.2 语义库示例（智慧体育）

| metric_code | 名称 | 公式 | 关联表/字段 |
|-------------|------|------|-------------|
| `participation_count` | 参与人数 | `COUNT(DISTINCT people_id)` | `sport_activity_qzs_record.people_id` |
| `checkin_times` | 打卡人次 | `COUNT(*)` | `sport_activity_qzs_record` |
| `checkin_completion_rate` | 打卡完成率 | 完成人数 / 应参与人数 | 完成表 + 参与表 |

术语与 `alias_json` 配合混合召回；**不再**依赖 `docs/TABLE_WHITELIST.md` 长期手工维护（文档仅作迁移参考）。

### 9.4 混合召回（向量 + 全文）

| 召回类型 | 数据源 | 索引 | 用途 |
|----------|--------|------|------|
| 字段语义 | `copilot_column_meta`（**effective** 描述 + alias） | ES `copilot_ask_column` | 「参与人数」→ `people_id` |
| 指标语义 | `copilot_metric_definition` | ES `copilot_ask_metric`（dense_vector） | 「打卡完成率」→ 指标口径 |
| 字段取值 | `copilot_field_value` | ES `copilot_ask_value`（text/keyword） | 「跳绳」→ `project_id=1` |
| 结构化补全 | `copilot_table_meta` / `copilot_table_relation` | MySQL 直查 | JOIN 路径、sch_id 列 |

**召回参数**（`settings.py` / 前端系统配置页只读展示）：

- `RECALL_TOP_K_COLUMN=8`
- `RECALL_TOP_K_METRIC=5`
- `RECALL_TOP_K_VALUE=10`
- `EMBEDDING_MODEL` 与 LLM 可同 Ollama base

**降级**：ES 不可用时回退 MySQL 关键词匹配（`alias_json` LIKE），记 span `recall_mode=keyword_fallback`。

### 9.5 前端配置（必须实现）

> **目标**：运营/超管**不写 SQL、不改代码**即可维护问数知识库；学校账户**只读问数**，不可进管理页。

#### 9.5.1 页面清单

| 路由 | 角色 | 功能 |
|------|------|------|
| `/admin/meta/tables` | ADMIN / OPERATOR | 表列表 CRUD；**输入表名读取业务库**；启用/停用 |
| `/admin/meta/tables/:id/columns` | ADMIN / OPERATOR | 字段列表：**类型+业务库备注只读**；**问数定义可编辑**；别名、角色 |
| `/admin/meta/tables/new` | ADMIN / OPERATOR | 向导：表名 →  introspect 预览 → 补人工定义 → 保存 |
| `/admin/meta/relations` | ADMIN / OPERATOR | 表关系 CRUD |
| `/admin/meta/field-values` | ADMIN / OPERATOR | 字段取值/枚举 CRUD |
| `/admin/meta/metrics` | ADMIN / OPERATOR | 指标 CRUD、关联字段、别名 |
| `/admin/meta/sql-examples` | ADMIN / OPERATOR | L1 样例 CRUD（含 match 规则 JSON） |
| `/admin/meta/index` | ADMIN / OPERATOR | 索引状态、一键重建、最近构建日志 |

#### 9.5.2 交互要求

- **录入新表**：输入 `tableName` → 点击「从业务库读取」→ 展示表 COMMENT 与字段列表（**字段名、类型、COLUMN_COMMENT**）→ 运营逐字段补充「问数定义」→ 保存入库。
- **已注册表**：「刷新结构」仅更新 auto 字段与新增列；人工定义不被覆盖（§9.2.5）。
- 字段页表格列：`字段名` | `类型(自动)` | `业务库备注(自动)` | `问数定义(人工)` | `有效定义(预览)` | `角色/别名`。
- 指标编辑支持 **可视化关联字段**（多选 `copilot_column_meta`）。
- 保存表/字段/指标/取值后提示 **「是否重建检索索引」**；索引重建异步任务，前端轮询状态。
- 所有写操作写 **审计日志**（`copilot_audit_log` 或独立 `copilot_meta_change_log`）。

### 9.6 评测问句（开放域为主）

L1 仅覆盖 subset；评测集侧重 **LLM + 混合召回** 路径（目标 **15～30 条** → `docs/EVAL_QUESTIONS.md`）：

1. 本校本月跳绳活动参与人数是多少？（可 L1 或 LLM）  
2. 本校最近 7 天每日参与人数趋势？  
3. 指定活动 ID 下各班级参与人数排名（前 10）？  
4. 本校今日完成打卡的学生人数？  
5. （超管）昨日全平台活动参与人次汇总？  
6. 本校跑步项目上周打卡人次？（字段取值召回）  
7. 对比本月跳绳与跑步参与人数？（多指标 + 过滤）  

**月验收**：开放域评测完成率 ≥ **60%**（第 4 周基线 70% 针对含 L1 命中；第 6 周单独统计 `degrade_level=0` 路径）。

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

### 10.6 元数据 / 语义库管理 API（`ADMIN` / `OPERATOR`）

前缀：`/api/v1/admin/meta`；均需 JWT；写操作记审计。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/introspect/tables/{tableName}` | **只读**拉取业务库：表 COMMENT + 字段类型/备注（**不落库**） |
| GET | `/tables` | 表元数据分页列表（含 effective 描述） |
| POST | `/tables` | 新增表（可带 columns 批量，含 manual 字段） |
| PUT | `/tables/{id}` | 更新 `description_manual`、grain、status 等 |
| POST | `/tables/{id}/refresh-from-business` | 刷新 auto 字段；**不覆盖**非空 manual |
| DELETE | `/tables/{id}` | 逻辑删除 |
| GET | `/tables/{id}/columns` | 字段列表（auto + manual + effective） |
| POST | `/tables/{id}/columns` | 批量保存字段（含 manual） |
| PUT | `/columns/{id}` | 更新 `description_manual`、别名、角色 |
| GET | `/relations` | 表关系列表 |
| POST | `/relations` | 新增关系 |
| GET | `/field-values` | 字段取值列表（可按 column_id 过滤） |
| POST | `/field-values` | 新增取值 |
| GET | `/metrics` | 指标列表 |
| POST | `/metrics` | 新增指标（含关联 column_ids） |
| PUT | `/metrics/{id}` | 更新指标与字段关联 |
| GET | `/sql-examples` | L1 样例列表 |
| POST | `/sql-examples` | 新增样例 |
| POST | `/sync-from-business` | 从 `information_schema` 增量同步 |
| POST | `/rebuild-index` | 异步重建 ES 向量/全文索引 |
| GET | `/index-jobs/{jobId}` | 查询索引构建状态 |

**`GET /introspect/tables/{tableName}` 响应示例**（只读预览，不写 copilot 库）：

```json
{
  "tableName": "sport_activity_qzs_record",
  "tableCommentAuto": "亲子活动打卡记录表",
  "existsInCopilot": false,
  "columns": [
    {
      "columnName": "people_id",
      "dataType": "bigint(20)",
      "columnCommentAuto": "学生ID",
      "isNullable": false,
      "ordinalPosition": 3
    },
    {
      "columnName": "sch_id",
      "dataType": "int(11)",
      "columnCommentAuto": "学校ID",
      "isNullable": true,
      "ordinalPosition": 5
    }
  ]
}
```

保存时前端提交 `descriptionManual`（表/字段）；后端持久化到 `description_manual`，检索与 Prompt 使用 **effective** 合并结果（§9.2.5）。

### 10.7 健康检查

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
| **`V004__meta_knowledge.sql`** | 表/字段/关系/取值/指标关联 DDL |
| **`/admin/meta/*`** | 元数据与语义库 CRUD + 同步 + 重建索引 |
| **`BusinessSchemaIntrospector`** | 只读 information_schema；供 introspect / refresh |
| **`description_manual` 优先级** | 同步/刷新不覆盖非空人工定义；effective 合并单测 |
| **`MetaKnowledgeService`** | MySQL → ES 向量/全文索引构建（索引用 effective 描述） |
| **`HybridRetriever`** | 问句混合召回，接入 LangGraph |
| **前端 meta 管理页** | §9.5 路由清单 |

---

## 12. 开发计划（6 周）

> **第 1～2 周已完成**（见 [PROGRESS.md](./PROGRESS.md)）。以下 **第 3～6 周** 为当前主攻：元数据知识库、语义库、前端配置、混合召回、多阶段推理。

### 第 1～2 周：地基 + LangGraph 基线 ✅

| 天 | 任务 | 交付物 | 状态 |
|----|------|--------|------|
| 1～2 | FastAPI + Vue + Docker 骨架 | 前后端可启动 | ✅ |
| 2～3 | `ddl_copilot.sql` + tracer + seed_admin | 审计可写 | ✅ |
| 3～4 | JWT + `role_policy` | 单测通过 | ✅ |
| 4～5 | `/ask` LangGraph 7 节点 + LLM | 问数可用 | ✅ |
| 5～7 | L1 样例 + 前端问数/用户管理 | 端到端 | ✅ |

---

### 第 3 周：元数据知识库 + 语义库（后端 + DDL）

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | `V004__meta_knowledge.sql`：含 `table_comment_auto` / `description_manual` / `column_comment_auto` 等 | 迁移脚本 |
| 2～3 | `BusinessSchemaIntrospector` + `GET /introspect/tables/{tableName}` | 前端可输入表名读字段类型与备注 |
| 3～4 | `refresh-from-business`（仅更新 auto，保护 manual）+ `seed_semantic_meta.py` | 优先级规则单测 |
| 4～5 | `MetaKnowledgeService` + ES client；`build_search_index.py` | 向量/全文索引可构建 |
| 5～7 | `/admin/meta/*` CRUD API（表/字段/关系/取值/指标） | Postman 可维护元数据 |

**周验收**：copilot 库有完整 meta 表；首表字段 ≥15 条；ES 索引构建成功；白名单改读 `copilot_table_meta`。

---

### 第 4 周：前端元数据/语义库管理页

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | `AdminMetaTables.vue`：**表名输入 + introspect 预览** + 双列备注（自动/人工） | 表/字段 CRUD |
| 2～3 | 字段子页：类型与业务库备注只读；问数定义可编辑；有效定义预览 | 人工优先规则可见 |
| 3～4 | 关系页 + 字段取值页 + 指标页（含字段关联） | 语义库可前端维护 |
| 4～5 | L1 样例管理页 + 索引重建页；路由守卫 ADMIN/OPERATOR | 运营自助闭环 |
| 5～7 | `feedback` API + badcase → 补 meta 或样例 | badcase 闭环 |

**周验收**：运营输入表名 → 读取业务库字段类型/备注 → 补充人工定义 → 保存 → 重建索引 → 问数验证；刷新结构后人工定义仍保留。

---

### 第 5 周：混合召回 + 多阶段 LangGraph

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | `app/retrieval/`：`HybridRetriever`（向量 + 全文 + MySQL 补全） | 单测：问句召回字段/指标/取值 |
| 2～3 | LangGraph 拆分：`extract_keywords` → 三路 `recall_*` → `merge` → `filter` → `build_llm_context` | span 可观测 |
| 3～4 | 改造 `generate_sql` Prompt；保留 L1 路由 | LLM 路径用结构化上下文 |
| 4～5 | `correct_sql` 节点（校验失败重试 1 次） | 降低幻觉 SQL |
| 5～7 | ES 不可用 keyword_fallback；`degrade_level` / 召回 detail 写入 span | 降级可追踪 |

**周验收**：开放域问句（非 L1）span 含 `recall_columns` / `recall_metrics` / `recall_values`；召回命中率可人工 spot check。

---

### 第 6 周：评测 + 试点 + 文档

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1～2 | `EVAL_QUESTIONS.md` 15～30 条 + `replay_eval.py`（分 L1 / LLM 路径统计） | 基线报告 |
| 2～3 | 限流、错误码统一；`META_KNOWLEDGE.md` 维护规范 | 运营文档 |
| 3～4 | 周报 SQL：P95、降级率、召回 fallback 率 | `WEEKLY_METRICS` 模板 |
| 4～5 | 部署文档、`.env.example` 补 Embedding/ES 变量 | 同事可复现 |
| 5～7 | 修 Top5 badcase（优先补 meta/指标，而非堆 L1） | **MVP 演示** |

**月验收标准（第 6 周末）**：

- [ ] 三类账户可用；学校账户**零串校**  
- [ ] 元数据/语义库可**前端完整维护**；索引可一键重建  
- [ ] 混合召回链路 span 完整；ES 故障可 keyword 降级  
- [ ] 评测集总完成率 ≥ 70%；**纯 LLM 路径（degrade_level=0）≥ 60%**  
- [ ] badcase → 补 meta/指标或 L1 样例闭环  

---

## 13. 风险与对策

| 风险 | 对策 |
|------|------|
| 业余时间不足 | 第 3 周先跑通**单表** meta + ES；暂缓多表 JOIN |
| LLM 成本高 | L1 保留 Top 高频；混合召回减少 Prompt 长度；限流 |
| 表结构复杂 | 白名单 5～15 张；`copilot_table_relation` 显式维护 JOIN |
| **元数据陈旧** | 前端「从业务库同步」+ 变更审计；badcase 优先补 meta |
| **召回不准** | 运营维护 alias/取值；span 记录 recall detail；A/B 调 Top-K |
| **ES 不可用** | keyword_fallback；/ready 探测 ES；索引重建 job 告警 |
| 学校账户未选校 | `active_sch_id` 为空 → 400，引导 `switch-school` |
| 默认超管密码泄露 | 生产必须改 `SEED_ADMIN_PASSWORD`；首次登录强制改密（二期） |
| 与体育后台账号两套 | 文档写清；避免用户混淆；二期再评估 SSO |
| SQL 注入 | sqlglot 解析 + 参数化 sch_id + 只读账号 |
| Docker 访问本机 MySQL 失败 | 使用 `host.docker.internal`；Linux 生产可改用宿主机 IP |
| RAGFlow 与 Ollama 抢 GPU | RAGFlow 用 CPU 版；LLM 走宿主机 Ollama；embedding 高峰勿与 14B 同时满载 |

---

## 14. Phase 2 backlog（MVP 之后）

- 对接体育后台 SSO  
- 学校账户跨绑定校汇总（`sch_id IN (...)`）  
- 渠道商租户模型  
- **SSE 流式**问数进度（对标 shopkeeper `/api/query`）  
- Langfuse / OpenTelemetry  
- 图表（AntV）  
- 可选 Qdrant 替代 ES 向量（大规模字段时）  
- RAGFlow 文档问答与问数并列（仍与 meta 库解耦）  

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

# ---------- Embedding（字段/指标向量，与 LLM 可同 Ollama）----------
EMBEDDING_API_BASE=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=qwen3-embedding:4b

# ---------- 混合召回 ----------
ELASTICSEARCH_URL=http://127.0.0.1:1200
ELASTICSEARCH_INDEX_PREFIX=copilot_ask_
RECALL_TOP_K_COLUMN=8
RECALL_TOP_K_METRIC=5
RECALL_TOP_K_VALUE=10
RECALL_KEYWORD_FALLBACK=true

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

# ---------- RAGFlow（可选，与问数 meta 解耦）----------
RAGFLOW_ENABLED=false
RAGFLOW_BASE_URL=https://127.0.0.1
```

### 15.3 本机 `development` 要点

```bash
APP_ENV=development
APP_DEBUG=true
LLM_API_BASE=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5-coder:7b
MYSQL_BUSINESS_HOST=127.0.0.1
MYSQL_COPILOT_HOST=127.0.0.1
ELASTICSEARCH_URL=http://127.0.0.1:1200
EMBEDDING_API_BASE=http://127.0.0.1:11434/v1
RAGFLOW_ENABLED=false
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

### 15.5 Embedding / ES 联调说明

1. 确保 Docker ES `:1200` 已启动；问数索引与 RAGFlow 索引通过 `ELASTICSEARCH_INDEX_PREFIX=copilot_ask_` 隔离。  
2. Embedding 默认走宿主机 Ollama（`EMBEDDING_*` 与 `LLM_*` 可同 base）。  
3. 首次或 meta 变更后：前端「重建索引」或 `python scripts/build_search_index.py`。  
4. Text2SQL **直接调 Ollama**；不依赖 RAGFlow 控制台。

### 15.6 RAGFlow 与 Ollama（可选）

1. RAGFlow 仅用于文档 RAG 实验，问数 meta 不入 RAGFlow 知识库。  
2. 容器访问宿主机 Ollama：`http://host.docker.internal:11434/v1`。

---

## 16. 部署清单速查

| 组件 | 本机 | 公司 |
|------|------|------|
| MySQL 5.7 | 已安装，建 `copilot` + 只读账号 | 同左，用内网地址 |
| Elasticsearch | Docker `:1200` | 运维统一部署 |
| Ollama + LLM + Embedding 模型 | 宿主机 | 内网 GPU 机或改云端 API |
| 问数 API | `uvicorn` 宿主机 :8000 | Docker / systemd |
| 问数前端 | `npm run dev` :5173（含 meta 管理页） | Nginx 静态 + 反代 API |
| RAGFlow（可选） | Docker | 与问数解耦 |

---

## 17. 相关代码索引（仅业务参考，禁止修改）

| 说明 | 位置 |
|------|------|
| 校维度报表示例 | `sport-plantform/.../SportActivityNewReportController` → `setSchId(getUser().getSchId())` |
| 旧系统角色命名对照 | `youplus-base/.../PeopleRoleType.java`（问数用 `ADMIN`/`OPERATOR`/`SCHOOL`） |
| 体育后台登录（不集成） | `sport-plantform/.../UserController#login` |

问数侧用户体系以本文 **§2.4** `copilot_sys_user` / `copilot_sys_user_school` 为准。

---

**文档版本**：v2.1  
**变更（v2.0）**：明确问数核心路线为 **元数据知识库 + 语义库（前端可配置）+ 向量/全文混合召回 + 多阶段 LangGraph**；计划由 4 周扩展为 **6 周**（第 3～6 周详述）；新增 §9  meta/语义库、§10.6 管理 API、§6.1 多阶段节点。  
**变更（v2.1）**：§9.2 区分 **自动读取**（`table_comment_auto` / `column_comment_auto` / `data_type`）与 **人工定义**（`description_manual`）；人工非空优先；新增 `GET /introspect/tables/{tableName}` 与前端表名录入向导。  
**维护**：随 meta 表结构、ES 索引、评测集更新同步改第 9、12、15 节；每完成里程碑更新 [PROGRESS.md](./PROGRESS.md)。

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
