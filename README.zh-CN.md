# Data Copilot

### Enterprise Natural-Language Analytics · 企业级智能问数平台

**语言 / Language:** [English](README.md) · **中文**

<p align="center">
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square" alt="License"/>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Vue-3-42b883?style=flat-square&logo=vuedotjs&logoColor=white" alt="Vue"/>
  <img src="https://img.shields.io/badge/FastAPI-Async-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/LangGraph-Multi--Agent-1C3C3C?style=flat-square" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/Security-SQL%20Guard%20%7C%20DataScope-b71c1c?style=flat-square" alt="Security"/>
</p>

<p align="center">
  <strong>用自然语言查询企业数据</strong> — 把固定报表交付周期从「周」缩短到「分钟」。<br/>
  面向中大型业务系统的 NL2SQL 子产品：元数据治理、混合召回、多阶段推理、SQL 安全网关与动态行级权限一体交付。
</p>

<p align="center">
  <a href="AGENTS.md">For AI Agents</a> ·
  <a href="docs/DEMO.md">Demo</a> ·
  <a href="#产品一览">产品一览</a> ·
  <a href="#系统配置--ai-模型与多引擎数据源">系统配置</a> ·
  <a href="#核心价值">核心价值</a> ·
  <a href="#系统架构">架构</a> ·
  <a href="#问数链路langgraph">问数链路</a> ·
  <a href="#快速开始">快速开始</a>
</p>

> **Open Source Demo (Scheme A)** — `make demo-up && make demo-smoke` · UI http://localhost:8080 · `admin` / `demo123456` · no API key (Fixture). Details: [AGENTS.md](AGENTS.md) · [docs/DEMO.md](docs/DEMO.md)

---

## 产品一览

问一句业务问题，系统自动完成 **记忆整理 → 知识库召回 → L1 样例精选 → SQL 规划与执行 → 图表生成与自然语言解读**，全程 SSE 流式可观测，每一步耗时与大模型推理过程可审计。

<p align="center">
  <img src="docs/images/ask-result.png" alt="问数结果：自然语言解读、SQL、图表与表格" width="920"/>
</p>
<p align="center"><em>问数工作台 · 自然语言解读 + SQL（ADMIN）+ 自动图表 / 表格 + 反馈闭环</em></p>

<p align="center">
  <img src="docs/images/ask-pipeline.png" alt="执行详情：各节点耗时与合计" width="920"/>
</p>
<p align="center"><em>执行详情 · 节点级进度与耗时，大模型推理过程可折叠查看</em></p>

---

## 系统配置 · AI 模型与多引擎数据源

管理台以 **Catalog（YAML）** 为唯一真相源配置 LLM 供应商与业务库类型，避免在业务代码里硬编码方言与厂商细节。支持 DeepSeek / 阿里云百炼 / OpenAI / Ollama 等模型接入，以及 MySQL、PostgreSQL、SQL Server、Oracle、ClickHouse、Doris、StarRocks、本地 Excel/CSV 等多引擎数据源；问数 SQL 生成、校验与执行均跟随当前默认库的方言与版本能力。

<p align="center">
  <img src="docs/images/admin-llm-providers.png" alt="添加模型：选择供应商向导" width="920"/>
</p>
<p align="center"><em>AI 模型配置 · 供应商卡片选型 · Chat / Embedding 角色分离 · 连通测试后落库</em></p>

<p align="center">
  <img src="docs/images/admin-datasource-wizard.png" alt="新建数据源：多引擎配置向导" width="920"/>
</p>
<p align="center"><em>业务数据源 · 多引擎向导 · 一键校验 · 设为默认问数库后即时切换方言上下文</em></p>

| 能力 | 说明 |
|------|------|
| LLM Catalog | `llm_providers.yaml` 驱动供应商列表、默认 API Base、建议模型 |
| Datasource Catalog | `datasource_types.yaml` 驱动可选引擎、表单 Schema、默认端口 |
| 密钥保护 | 配置项密文落库（Fernet），接口仅回显掩码 |
| SQL 方言 | `ResolvedSqlContext` 贯通 Prompt / sqlglot / Guard / 执行器 |
| 可选驱动 | `pip install -e ".[db-pg,db-mssql,db-ch,db-oracle,db-excel]"` |

---

## 核心价值

| 维度 | 传统方案 | Data Copilot |
|------|----------|--------------|
| 需求响应 | 每个新问题走 PRD → 开发 → 发版 | 运营配置元数据 / L1 样例，或 LLM 即时生成 |
| 数据安全 | 报表接口分散，权限难统一 | 表白名单 + AST 校验 + **配置驱动 DataScope** + 只读连接 |
| 口径一致 | 口径散落在代码与文档 | 语义库（指标定义、别名、公式）驱动召回与 Prompt |
| 可观测 | 黑盒接口，问题难追溯 | 全链路 Trace / Span / Audit，支持 badcase 闭环 |
| 知识沉淀 | 业务逻辑锁死在 Java/SQL | Git 代码知识图谱 + 表字段 meta 融合召回 |
| LLM 风险 | 易被注入指令绕过业务规则 | **不信任模型输出**：Prompt 定界 + sql_guard 执行层 Fail-closed |
| 数据源扩展 | 改代码适配新库 | Catalog + Connector 注册，方言随默认库切换 |

**典型场景**：「本部门本月核心指标是多少？」「最近 7 天每日趋势？」「全平台昨日汇总？」—— 系统自动理解意图、经动态权限校验后生成只读 SQL，返回表格与自然语言解读。

**当前里程碑**：Agent Plan/Tool Loop、Git 代码知识图谱、配置驱动 DataScope、Prompt 定界与注入评测、**多引擎数据源 / LLM 管理台** 已落地；详见 [docs/02-PROGRESS.md](docs/02-PROGRESS.md)。

---

## 系统架构

```mermaid
flowchart TB
    subgraph Client["接入层"]
        UI["Vue3 问数控制台"]
        Admin["元数据 / 语义 / 系统配置"]
    end

    subgraph API["应用层 · FastAPI"]
        Auth["JWT 认证 · 多角色 RBAC"]
        Ask["/ask 问数编排"]
        Meta["/admin/meta 元数据 API"]
        Sys["/admin/system LLM · 数据源"]
        Scope["/admin  DataScope API"]
        Obs["可观测 · Tracer"]
    end

    subgraph Agent["推理层 · LangGraph"]
        Recall["多路混合召回"]
        Plan["Plan · Agent Tool Loop"]
        SQLGen["SQL 生成 · 校验 · 修正"]
        Exec["分步执行 · 语义验证"]
    end

    subgraph Security["安全层"]
        PB["Prompt 定界 / 召回清洗"]
        Guard["SQL Guard · DataScope 注入"]
    end

    subgraph Knowledge["知识层"]
        MySQLMeta[("MySQL copilot 库<br/>元数据 · 语义 · 审计 · Scope")]
        Zvec["Zvec 进程内索引<br/>向量 + 全文 · RRF 混合召回"]
        ES["Elasticsearch（可选）<br/>RAGFlow / VECTOR_STORE=elasticsearch"]
        CodeKG["Git 代码知识图谱<br/>Artifact · 调用关系"]
    end

    subgraph Data["数据层"]
        BizDB[("业务库 · 多引擎只读<br/>MySQL / PG / CH / Excel …")]
        LLM["LLM / Embedding<br/>Catalog 配置 · OpenAI 兼容"]
    end

    UI --> Auth
    Admin --> Meta
    Admin --> Scope
    Admin --> Sys
    UI --> Ask
    Ask --> Agent
    Auth --> Ask
    Agent --> Recall
    Recall --> Zvec
    Recall --> ES
    Recall --> MySQLMeta
    Recall --> CodeKG
    Agent --> PB
    PB --> LLM
    Plan --> LLM
    SQLGen --> Guard
    Guard --> BizDB
    Exec --> BizDB
    Obs --> MySQLMeta
    Meta --> MySQLMeta
    Sys --> MySQLMeta
    Sys --> LLM
    Sys --> BizDB
```

### 部署拓扑

```text
┌──────────────────────────────────────────────────────────────────────┐
│  应用宿主机                                                           │
│  · Python Uvicorn :8000    ← 问数 API（开发 / Docker 生产）           │
│  · Vue Vite :5173          ← 前端（开发）；生产为静态资源 + Nginx      │
│  · Ollama / 内网 LLM       ← 大模型 + Embedding（亦可在管理台配置）    │
│  · MySQL 5.7+              ← copilot 治理库（元数据 · 审计 · 系统配置） │
│  · 业务库（多引擎只读）    ← MySQL / PG / SQL Server / CH / Excel …   │
│  · Zvec（默认）            ← 问数元数据向量/全文索引，数据目录 data/zvec   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ host.docker.internal（可选）
┌───────────────────────────────▼──────────────────────────────────────┐
│  可选基础设施（Docker Compose · RAGFlow 栈）                            │
│  · Elasticsearch :1200     ← RAGFlow 依赖；问数可设 VECTOR_STORE=elasticsearch │
│  · Redis / MinIO（可选）     ← 文档 RAG 栈，与问数元数据索引解耦              │
└──────────────────────────────────────────────────────────────────────┘
```

**设计原则**：业务库与治理库分离；问数仅在独立库 `copilot` 中建表，对业务库 **零侵入、只读访问**；LLM 与数据源连接信息经管理台加密落库，运行时按默认项解析。

---

## 问数链路（LangGraph）

单次 `/ask` 请求经 **30+ 节点** 的有向图编排，支持 SSE 流式进度推送。

```mermaid
flowchart LR
    subgraph Phase1["① 上下文"]
        N1[normalize_question]
        N2[session / preference / 指代消解]
    end

    subgraph Phase2["② 混合召回"]
        K[extract_keywords]
        T[recall_tables]
        C[recall_columns]
        M[recall_metrics]
        F[recall_field_values]
        Merge[merge · filter · build_llm_context]
        L1[select_l1_examples]
    end

    subgraph Phase3["③ 推理"]
        P[plan_question]
        AL[agent_loop<br/>MySQL meta + 代码工具]
        GS[generate_sql / generate_sql_step]
    end

    subgraph Phase4["④ 安全与执行"]
        V[validate_sql]
        CS[correct_sql]
        AP[apply_policy · DataScope]
        EX[execute_sql · 分步 SQL]
        VF[verify_answer]
        FA[format_answer]
    end

    N1 --> N2 --> K --> T --> C --> M --> F --> Merge --> L1
    L1 --> P
    P -->|简单问句| GS
    P -->|复杂问句| AL --> GS
    GS --> V
    V -->|失败| CS --> V
    V -->|通过| AP --> EX --> VF --> FA
```

### 时序图：一次完整问数

```mermaid
sequenceDiagram
    actor User as 业务用户
    participant FE as Vue 前端
    participant API as FastAPI
    participant Graph as LangGraph
    participant Zvec as Zvec 索引
    participant LLM as 大模型
    participant Guard as SQL Guard
    participant DB as 业务只读库

    User->>FE: 输入自然语言问题
    FE->>API: POST /api/v1/ask (+ JWT)
    API->>API: load_effective_policy（DataScope 开启时）
    API->>Graph: 启动 AskGraph (trace_id)

    Graph->>Graph: 加载会话记忆 / 用户偏好（定界后注入 Prompt）
    Graph->>Zvec: 混合召回（表/字段/指标/取值/代码，向量+全文 RRF）
    Zvec-->>Graph: Top-K 上下文
    Graph->>LLM: Plan / Agent 工具循环（System 拒令 + 不可信定界）
    LLM-->>Graph: SQL 草案

    opt L1 样例精选
        Graph->>Zvec: 召回 Top-K L1 候选
        Graph->>LLM: 精选 0~3 条注入规划 Prompt
    end

    Graph->>Guard: AST 解析 · 表白名单 · deny 列 · LIMIT
    Guard-->>Graph: final_sql
    Graph->>Guard: Scope 注入 / grant 外字面量校验
    Graph->>DB: 只读 SELECT 执行
    DB-->>Graph: 结果集
    Graph->>LLM: 语义验证 + 自然语言解读
    Graph->>API: AskResponse (+ spans 写入审计库)
    API-->>FE: JSON 或 SSE done 事件
    FE-->>User: 表格 + 解读文案
```

---

## 技术亮点

### 1. 三层知识融合

```text
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  结构化元数据    │   │  语义指标库      │   │  代码知识图谱    │
│  表/字段/关系    │ + │  口径/别名/公式  │ + │  Git 同步解析    │
│  information_   │   │  L1 SQL 样例     │   │  Java/MyBatis   │
│  schema 半自动   │   │  badcase 闭环    │   │  Zvec/ES 向量召回 │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         └─────────────────────┼─────────────────────┘
                               ▼
                    HybridRetriever → LLM Context
```

- **向量召回**：字段 / 指标语义相似度（Zvec HNSW + cosine；可选 ES `dense_vector`）
- **全文召回**：枚举取值、业务术语（Zvec FTS / BM25；字段 `search_text`）
- **混合重排（Zvec 默认）**：向量 + 全文双路查询，**RRF（Reciprocal Rank Fusion）** 融合排序
- **结构化补全**：MySQL 元数据 + keyword 降级（检索后端不可用时仍可服务）

### 问数检索：Zvec（默认）与 Elasticsearch（可选）

问数链路的表 / 字段 / 指标 / 字段取值 / 代码 Artifact 索引，**默认使用 [Zvec](https://zvec.org/) 进程内向量库**，无需单独部署 Elasticsearch。

| 能力 | Zvec（`VECTOR_STORE=zvec`） | Elasticsearch（`VECTOR_STORE=elasticsearch`） |
|------|----------------------------|-----------------------------------------------|
| 部署 | 嵌入式，`ZVEC_DATA_DIR` 持久化 | 需 ES 服务（如 RAGFlow 栈 `:1200`） |
| 向量检索 | HNSW + cosine | kNN `dense_vector` |
| 全文检索 | FTS（jieba 分词） | `match` 全文 |
| 混合召回 | 向量 + FTS + **RRF rerank** | 向量单路（或自行扩展） |
| 列召回过滤 | 查询侧 `filter`（按 `table_name`） | 内存 over-fetch 后过滤 |
| 索引重建 | 管理 API / `build_search_index.py` | 同上（切换后端） |

**配置（`backend/.env.development`）**：

```env
VECTOR_STORE=zvec
ZVEC_DATA_DIR=data/zvec
ZVEC_INDEX_PREFIX=copilot_ask_
RECALL_HYBRID_RERANK=true
RECALL_RERANK_FETCH_MULTIPLIER=3
RECALL_RRF_RANK_CONSTANT=60
```

**索引 collection**（前缀 `copilot_ask_`）：`table`、`column`、`metric`、`value`（仅全文）、`code_artifact`。

**重建索引**（元数据变更后）：

```powershell
cd backend
$env:APP_ENV = "development"
python scripts/build_search_index.py
# 或管理端 POST /api/v1/admin/meta/rebuild-index
```

**切换回 ES**（与 RAGFlow 共用集群时）：安装可选依赖 `pip install -e ".[legacy-es]"`，设置 `VECTOR_STORE=elasticsearch` 与 `ELASTICSEARCH_URL`。工厂见 `app/retrieval/search_index.py`（`AskZvecClient` / `AskElasticsearchClient`）。

**注意**：多进程部署时 Zvec 写索引宜单 worker 或独立 job；问数只读召回可多进程并发。

### 2. SQL 安全网关（Defense in Depth）

| 层级 | 机制 |
|------|------|
| 连接层 | 业务库独立只读账号，`assert_business_readonly_sql` |
| 语法层 | sqlglot AST：仅允许单条 `SELECT`，禁止多语句 |
| 范围层 | 动态表白名单（`copilot_table_meta` + 用户 `table_grant`） |
| 权限层 | **DataScope**：按维度绑定列注入 `IN` / 校验 grant 外字面量 |
| 列级层 | **column_deny** AST 遍历，敏感列拒绝（`COLUMN_DENIED`） |
| 资源层 | 自动追加 `LIMIT`，防大结果集拖垮库 |
| 修正层 | `correct_sql` 校验失败时 LLM 自我修正（有限重试） |

**核心原则**：无论 Prompt 如何构造，越权 SQL **必须在网关层被拒绝**，不依赖模型「听话」。

### 3. 配置驱动 DataScope（RBAC + 行级授权）

平台采用 **RBAC + DataScope** 双层模型：角色决定「能做什么」，`dimension_code` + grant 决定「能看哪些行」。

```text
超级管理员 ──► bypass · 用户管理 · 元数据治理
运营管理员 ──► 须配置 grant 后方可问数（默认拒绝）
学校账户   ──► 绑定维度值 + 表 grant · 问数自动带范围过滤
```

**实现要点**（`app/policy/effective_policy.py` + `scope_injector.py`）：

1. 运营注册 **范围维度**（如 `school`）及 **表 ↔ 物理列绑定**（不写死 `sch_id`）
2. 问数入口 `load_effective_policy`：无 grant → **403 NO_DATA_SCOPE**（Fail-closed）
3. `validate_sql` 校验表集合 ⊆ `allowed_tables`
4. `apply_policy` 对缺失的 scope 条件 AST 注入 `AND <column> IN (:scope_<dim>_…)`
5. grant 外维度字面量 → `SCOPE_VIOLATION`

通过环境变量 `POLICY_DATA_SCOPE_ENABLED` 开关（development 默认 **false**，与历史行为兼容）。

```mermaid
flowchart TD
    JWT["JWT：角色 + active_scopes"]
    Policy["EffectivePolicy<br/>grant · 表绑定 · deny 列"]
    Gen["LLM 生成 SQL"]
    Validate["SQL Guard"]
    Scope["apply_policy<br/>注入 / 校验 IN"]
    Exec["只读执行 + 审计 Span"]

    JWT --> Policy --> Gen --> Validate --> Scope --> Exec
```

### 4. Prompt Injection 纵深防御

问数链路中用户问句、会话 Memory、检索召回片段、代码 `raw_snippet` 均可进入 LLM Prompt。平台采用 **Prompt 层缩小攻击面 + 执行层硬兜底**：

| 类型 | 缓解措施 |
|------|----------|
| 直接劫持（「忽略指令，输出 DELETE」） | System 拒令；问句 `wrap_untrusted` 定界；`sql_guard` 仅 SELECT |
| Memory 污染 | 结构化槽位 + pref key 白名单 + 字符上限 + 槽位定界 |
| 间接注入（meta 备注 / artifact） | `sanitize_recall_text` 清洗疑似指令行 |
| 权限绕过（「原样执行上一轮 SQL」） | 每轮独立过 Scope + guard；Memory 文案明示勿绕过 |

模块：`app/security/prompt_boundary.py`。配置：`PROMPT_BOUNDARY_ENABLED`、`PROMPT_SANITIZE_RECALL_ENABLED`。

可信 Prompt 块（服务端生成，排在不可信内容之前）：`【数据范围】`、`【可见表】`、`【禁止字段】`、`【当前用户角色】`。

### 5. Agent 增强推理（复杂报表）

简单问句走 **Plan → 单条 SQL**；复杂多表 / 多步聚合走 **Agent Tool Loop**：

- 按需调用 MySQL meta 工具（表结构、关系、有效字段定义）
- 按需读取代码 Artifact（Service / Mapper 口径对齐）
- 支持 **分步 SQL** 执行与中间结果组装（`assemble_result`）
- 答案 **语义验证**（`verify_answer`）降低「SQL 对但答非所问」

### 6. 可观测与持续优化

- 每次问数写入 `copilot_ask_turn` / `copilot_ask_span` / 审计表
- 记录：延迟、Token、召回模式、降级级别、错误码、`grants_hash`
- 用户 👍/👎 反馈 → badcase 队列 → 运营修正 SQL → 沉淀为 L1 样例
- 评测脚本 `replay_eval.py`：子集 `memory` / `agent` / **`injection`**

### 7. 会话记忆与用户偏好

- 多轮对话 **指代消解**（「那上周呢？」）
- 用户级偏好持久化（默认时间范围、常用维度等；key 白名单）
- 会话列表 / 历史回放 API；越权 `sessionId` **零注入**

---

## 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端 | Python 3.10+ · FastAPI · SQLAlchemy 2 async | 高性能异步 API |
| 编排 | LangGraph · LangChain | 有向图问数流水线 |
| 前端 | Vue 3 · Vite · Pinia | 问数对话 + 元数据管理后台 |
| 数据库 | MySQL 5.7+ | 双库：业务只读 + copilot 治理 |
| 检索 | **Zvec**（默认）· Elasticsearch 8.x（可选） | 向量 + 全文混合召回；RRF rerank |
| LLM | Ollama / 通义 / DeepSeek 等 | OpenAI 兼容 `chat/completions` |
| 安全 | JWT · bcrypt · sqlglot · DataScope · Prompt 定界 | 认证 + AST 校验 + 注入防护 |
| 部署 | Docker Compose · Uvicorn | 后端容器化；DB/LLM 宿主机 |

---

## 仓库结构

```text
data-copilot-bot/
├── backend/
│   ├── app/
│   │   ├── agent/          # LangGraph 图、召回、Plan、Agent Loop
│   │   ├── ask/            # 问数服务、L1 精选
│   │   ├── auth/           # JWT、用户仓储
│   │   ├── policy/         # EffectivePolicy、ScopeInjector、role_policy
│   │   ├── security/       # Prompt 定界、召回清洗（prompt_boundary）
│   │   ├── meta/           # 元数据 CRUD、检索索引构建
│   │   ├── retrieval/      # HybridRetriever、Zvec/ES Client（search_index 工厂）
│   │   ├── sql/            # SQL Guard、白名单、列 deny
│   │   ├── code/           # Git 同步、代码解析、知识图谱
│   │   ├── memory/         # 会话记忆、用户偏好
│   │   ├── observability/  # Tracer、Span 写入
│   │   └── api/            # REST 路由（含 admin_scope）
│   ├── scripts/
│   │   └── sql/copilot/    # V001～V010 版本迁移（含 DataScope）
│   ├── tests/              # pytest（guard / scope / injection / agent）
│   └── deploy/             # Docker Compose
├── frontend/
│   └── src/
│       ├── views/          # Ask、Login、AdminMeta*、AdminUsers、AdminCodeRepos
│       └── api/            # 后端 API 封装
└── docs/                   # 编号索引见 docs/README.md
    ├── README.md           # 计划索引与阅读顺序
    ├── 01-MVP_DEVELOPMENT_PLAN.md
    ├── 02-PROGRESS.md
    ├── 03-PHASE2_ROADMAP.md
    ├── 16-DIALOGUE_GATE_PLAN.md
    ├── 20-OPENSOURCE_GROWTH_PLAN.md  # 开源化与涨星
    └── 90～94 规范 / 评测 / Embed / MCP
```

---

## 核心 API 一览

| 方法 | 路径 | 能力 |
|------|------|------|
| POST | `/api/v1/auth/login` | 登录，签发 JWT |
| POST | `/api/v1/auth/switch-school` | 学校账户切换当前校 |
| GET | `/api/v1/auth/me` | 当前用户上下文 |
| POST | `/api/v1/ask` | 自然语言问数（支持 SSE 流式） |
| POST | `/api/v1/ask/cancel` | 中断进行中的问数 |
| GET/POST | `/api/v1/sessions` | 会话管理 |
| PUT | `/api/v1/memory/preferences` | 用户偏好（key 白名单） |
| POST | `/api/v1/feedback` | 问数反馈 / badcase |
| GET/POST | `/api/v1/admin/meta/*` | 元数据、语义库、L1 样例 CRUD |
| GET/POST | `/api/v1/admin/meta/scope-dimensions` | 范围维度注册 |
| PUT | `/api/v1/admin/meta/tables/{id}/scope-bindings` | 表 ↔ 维度 ↔ 列绑定 |
| POST | `/api/v1/admin/meta/column-deny` | 敏感列 deny |
| PUT | `/api/v1/admin/users/{id}/data-grants` | 用户行级授权 |
| PUT | `/api/v1/admin/users/{id}/table-grants` | 用户表级 allow |
| POST | `/api/v1/admin/meta/rebuild-index` | 重建问数检索索引（Zvec / ES） |
| GET/POST | `/api/v1/admin/code/*` | Git 仓库同步、代码索引 |
| GET/POST | `/api/v1/admin/users` | 超管用户管理 |
| GET | `/health` · `/ready` | 存活探针（含 MySQL / `search_index`） |

完整 OpenAPI 文档：启动后端后访问 `/docs`。

---

## 快速开始

### 开源 Demo（推荐 · 无需宿主机 MySQL / API Key）

```bash
make demo-up && make demo-smoke
# Windows: .\scripts\demo_up.ps1 ; .\scripts\demo_smoke.ps1
```

打开 http://localhost:8080 ，账号 `admin` / `demo123456`。详见 [AGENTS.md](AGENTS.md) · [docs/DEMO.md](docs/DEMO.md)。

### 环境要求（本地开发 / 公司现网）

| 组件 | 说明 |
|------|------|
| MySQL 5.7+ | 业务库（只读）+ `copilot` 治理库 |
| Python 3.10+ | 后端运行时 |
| Node.js 18+ | 前端构建 |
| Zvec 0.5+（默认） | 问数混合召回；`pip install zvec`，数据目录 `ZVEC_DATA_DIR` |
| Elasticsearch 8.x（可选） | `VECTOR_STORE=elasticsearch` 或 RAGFlow 栈 |
| Ollama 或兼容 API | LLM + Embedding |

### 后端

```powershell
cd backend
copy .env.example .env.development
# 编辑 MySQL、JWT、LLM、ZVEC_DATA_DIR 等配置

$env:APP_ENV = "development"
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"

# 初始化 copilot 库（按版本顺序执行 scripts/sql/copilot/V*.sql）
mysql -u root -p copilot < scripts/sql/copilot/V001__init_copilot_tables.sql
# … 依次执行至 V010__data_scope.sql（启用 DataScope 时需要）
python scripts/seed_admin.py

# 元数据注册后重建 Zvec 问数索引（需 Ollama embedding 可用）
python scripts/build_search_index.py

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 启用 DataScope（可选 · 生产建议）

```powershell
# 1. 执行 V010 迁移
mysql -u copilot -p copilot < scripts/sql/copilot/V010__data_scope.sql

# 2. 从 copilot_sys_user_school 迁移 school 维度 grant
python scripts/seed_data_scope.py

# 3. backend/.env.development 中设置
# POLICY_DATA_SCOPE_ENABLED=true
# POLICY_DEFAULT_DENY=true
```

启用后，非 ADMIN 用户须在管理 API 中配置 **表 grant** 与 **行级 data grant**，否则问数返回 `403 NO_DATA_SCOPE`。

### 前端

```powershell
cd frontend
copy .env.example .env.development
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。

### 测试与评测

```powershell
cd backend
$env:APP_ENV = "development"
pytest tests/ -q

# 需 API 已启动 + 有效 JWT
python scripts/replay_eval.py --subset memory --token "<JWT>"
python scripts/replay_eval.py --subset agent --token "<JWT>"
python scripts/replay_eval.py --subset injection --token "<JWT>"
```

注入子集验收指标：`injection_blocked_rate=100%`，`leaked_sql_count=0`（无 DELETE/DML 类 SQL 被执行）。

### Docker 部署（后端 API）

```powershell
cd backend
copy .env.example .env.production
docker compose -f deploy/docker-compose.yml up -d --build
```

---

## 数据模型（治理库概要）

```mermaid
erDiagram
    copilot_sys_user ||--o{ copilot_user_data_grant : "行级授权"
    copilot_sys_user ||--o{ copilot_user_table_grant : "表级 allow"
    copilot_scope_dimension ||--o{ copilot_table_scope_binding : binds
    copilot_table_meta ||--o{ copilot_table_scope_binding : has
    copilot_table_meta ||--o{ copilot_column_meta : has
    copilot_table_meta ||--o{ copilot_table_relation : joins
    copilot_metric_definition ||--o{ copilot_metric_column : maps
    copilot_ask_turn ||--o{ copilot_ask_span : traces
    copilot_git_repo ||--o{ copilot_code_artifact : syncs

    copilot_scope_dimension {
        varchar code PK "school / region …"
        varchar value_type "int|string"
    }
    copilot_user_data_grant {
        bigint user_id
        varchar dimension_code
        json values_json "IN 列表"
    }
    copilot_table_meta {
        bigint id PK
        varchar table_name UK
        tinyint status
    }
    copilot_ask_turn {
        varchar trace_id UK
        varchar status
        int latency_ms
    }
```

---

## 质量保障

- **单元测试**：SQL Guard、DataScope、Prompt 定界/注入、元数据、LangGraph、Agent 工具等 **180+** 用例
- **评测回归**：`replay_eval.py` 支持 `memory` / `agent` / **`injection`** 子集
- **badcase 闭环**：运营修正 SQL → 沉淀 L1 → 同类问句直出（Phase 2 将扩展为**术语库 + 审核发布台**，见 [03-PHASE2_ROADMAP.md](docs/03-PHASE2_ROADMAP.md)）
- **安全回归**：`tests/test_prompt_injection.py` + `docs/eval/prompt_injection.json`

---

## 扩展阅读

| 文档 | 内容 |
|------|------|
| [docs/README.md](docs/README.md) | **文档索引**：编号规则与阅读顺序 |
| [docs/01-MVP_DEVELOPMENT_PLAN.md](docs/01-MVP_DEVELOPMENT_PLAN.md) | 完整架构、14 周里程碑、§14 Phase 2 backlog |
| [docs/03-PHASE2_ROADMAP.md](docs/03-PHASE2_ROADMAP.md) | **Phase 2 三大优先级**：Chart SSR、运营闭环、MCP/iframe |
| [docs/12-CHART_VISUALIZATION_PLAN.md](docs/12-CHART_VISUALIZATION_PLAN.md) | 图表展示：Plan 意图识别、chartSpec、历史回放；SSR 见 Phase 2 §P2-A |
| [docs/16-DIALOGUE_GATE_PLAN.md](docs/16-DIALOGUE_GATE_PLAN.md) | 对话门禁与多轮澄清：闲聊短路、缺槽追问、召回/Plan 闸门 |
| [docs/20-OPENSOURCE_GROWTH_PLAN.md](docs/20-OPENSOURCE_GROWTH_PLAN.md) | **开源化与涨星**：方案 A（Compose MySQL 8）、**AI Agent 一键跑通**、评测、传播 |
| [docs/02-PROGRESS.md](docs/02-PROGRESS.md) | 模块完成度与联调清单 |
| [docs/92-EVAL_QUESTIONS.md](docs/92-EVAL_QUESTIONS.md) | 评测问句（含 inj-* 注入子集） |
| [docs/91-PROMPT_SECURITY.md](docs/91-PROMPT_SECURITY.md) | 威胁模型、定界符约定、运营规范 |

---

## License

[Apache License 2.0](LICENSE)。部署前请替换 `JWT_SECRET`、`SEED_ADMIN_PASSWORD` 等敏感配置；生产启用 DataScope 前须完成相关迁移与用户 grant 配置，并遵循所在组织的数据安全规范。
