# 开源化与涨星增长 · 详细计划

> **状态**：🟡 P0～P1.5 已落地代码（方案 A Demo）；P2～P5 待做  
> **版本**：v1.5 · 2026-08（落地：Compose MySQL8 + Fixture + `make demo-up` / `AGENTS.md`）  
> **目标**：把 Data Copilot 做成 **可发现、可一键跑通、人和 AI Agent 都能流畅启动** 的开源问数项目，在 8～12 周内具备稳定涨星基础。  
> **关联**：[docs/README.md](./README.md) 索引、[02-PROGRESS.md](./02-PROGRESS.md)、[03-PHASE2_ROADMAP.md](./03-PHASE2_ROADMAP.md)

---

## 目录

1. [背景与现状诊断](#1-背景与现状诊断)
2. [目标与非目标](#2-目标与非目标)
3. [核心叙事（对外怎么说）](#3-核心叙事对外怎么说)
4. [总体里程碑](#4-总体里程碑)
5. [P0 · 开源准入（Week 1）](#5-p0--开源准入week-1)
6. [P1 · 五分钟可跑通 Demo（Week 2～4）](#6-p1--五分钟可跑通-demoweek-24)
7. [P1.5 · AI Agent 友好启动（与 P1 同迭代）](#7-p15--ai-agent-友好启动与-p1-同迭代)
8. [P2 · README 与发现入口（Week 3～5）](#8-p2--readme-与发现入口week-35)
9. [P3 · 可验证评测与对比（Week 4～6）](#9-p3--可验证评测与对比week-46)
10. [P4 · 社区与传播（Week 5～8）](#10-p4--社区与传播week-58)
11. [P5 · 持续运营（Week 8～12）](#11-p5--持续运营week-812)
12. [任务分解与责任](#12-任务分解与责任)
13. [验收标准（DoD）](#13-验收标准dod)
14. [风险与降级](#14-风险与降级)
15. [与现有路线图的关系](#15-与现有路线图的关系)

---

## 1. 背景与现状诊断

### 1.1 已有优势（技术厚度够）

| 资产 | 开源卖点 |
|------|----------|
| LangGraph 多阶段问数 + Agent Tool Loop | 「真 Agent」，不是单次 Prompt 出 SQL |
| SQL Guard + DataScope Fail-closed | **安全差异化**（多数 NL2SQL 弱项） |
| 元数据 / 指标 / 代码图谱三路召回 | 企业口径与代码落地 |
| 多引擎 Datasource Catalog | MySQL / PG / CH / Excel… 可配置扩展 |
| SSE 全链路可观测 | 演示与排障友好 |
| 已有截图、`docs/eval/` 评测集 | 可快速做成公开报告 |

### 1.2 当前涨星卡点（必须先修）

对照仓库现状（2026-08）：

| 卡点 | 现状 | 影响 |
|------|------|------|
| **协议** | README badge `License-Proprietary`，无 `LICENSE` 文件 | 无法被 Awesome 列表 / 企业二次使用 |
| **GitHub About** | `description` / `topics` / `homepage` 均为空 | 搜索与推荐几乎为零 |
| **一键运行** | Compose 依赖宿主机 MySQL 5.7 / Ollama | 围观者装不起来 → 不 star；**方案 A**：镜像内 MySQL 8 治理库，无需改读写方言 |
| **README 叙事** | 偏企业白皮书（长架构、多节点） | 前 30 秒抓不住人 |
| **语言** | 以中文为主 | 错过 GitHub 英文流量主场 |
| **在线 Demo** | 无公开试用 | 转化漏斗断裂 |
| **社区基建** | 无 ISSUE/PR 模板、无 CONTRIBUTING | 难以把围观变贡献 |
| **AI 可启动性** | 无 `AGENTS.md` / 无单一入口命令；依赖本机 MySQL 与手工步骤 | Clone 后 Cursor/Copilot 等 Agent 容易卡死、乱改配置 |

**结论**：功能已具备「能涨」的条件；短板是 **协议、可运行性（含 AI 无脑启动）、发现入口、叙事与传播**。

---

## 2. 目标与非目标

### 2.1 目标

1. **合法开源**：明确 OSI 兼容协议（推荐 Apache-2.0），去掉 Proprietary 标识。  
2. **五分钟跑通**：陌生人克隆后，按 README 三条命令能问出第一句样例数据。  
3. **AI 流畅启动**：任意 Coding Agent（Cursor / Claude Code / Copilot 等）clone 后，读仓库根指引即可 **一条命令** 起 Demo，默认 **无云端 Key** 也能完成样例问数（Fixture）。  
4. **可发现**：GitHub About + Topics + 中英 README 齐全。  
5. **可验证**：公开至少一组评测数字（准确率 / 注入阻断率）+ 竞品对比表。  
6. **可传播**：有 Demo GIF / 可选在线 Demo + 至少 1 篇技术长文冷启动。  
7. **可贡献**：Issue/PR 模板 + Good First Issues ≥ 5。

### 2.2 非目标（本计划不做）

- 不追求一次性冲上「万星」；本计划只建立 **可持续增长漏斗**。  
- 不在开源版默认暴露公司真实业务库、真实学校数据。  
- 不把内部智慧体育专属口径硬编码进开源 Demo（用虚构样例域）。  
- 不替代 [03-PHASE2_ROADMAP.md](./03-PHASE2_ROADMAP.md) 的产品功能优先级；二者并行，Demo 最小可用即可。  
- 暂不承诺企业 SLA / 商业支持体系（可后续单独立项）。

### 2.3 成功指标（建议）

| 时间窗 | 指标 | 目标 |
|--------|------|------|
| W2 | License + About + Topics 上线 | 100% |
| W4 | `docker compose up` 样例问数成功 | 贡献者自测通过 |
| W4 | **AI 盲测**：新对话仅给仓库路径，Agent 能自行 up + smoke | ≥1 次成功录像/日志 |
| W6 | README 英文版 + Demo GIF | 合并主分支 |
| W8 | 公开评测报告 + 对比表 | 1 份 |
| W8～W12 | GitHub Stars（参考） | 相对基线明显增长；更看 **Clone / Unique visitor / Issue** |
| W12 | Good First Issues 被认领 | ≥ 2 |

> Star 数受传播运气影响大；以 **可跑通率、文档停留、Issue 质量** 为过程指标更可靠。

---

## 3. 核心叙事（对外怎么说）

### 3.1 一句话定位（中英）

- **中文**：企业级自然语言问数 —— **SQL 安全网关 + 行级权限 + 多引擎**，开箱可演示。  
- **English**: Enterprise NL2SQL with **fail-closed SQL Guard, row-level DataScope, and multi-engine catalogs** — not just another Chat-to-SQL toy.

### 3.2 差异化三点（必须反复出现）

1. **Fail-closed Security**：表白名单 · AST · column_deny · DataScope —— 不信任模型输出。  
2. **Knowledge Fusion**：表字段 meta + 指标口径 +（可选）代码图谱。  
3. **Ops-ready**：Catalog 配置 LLM/数据源、SSE 可观测、badcase → L1 闭环（Phase 2 强化）。

### 3.3 避免的表述

| 少写 | 多写 |
|------|------|
| 「30+ LangGraph 节点」 | 「问一句 → 安全 SQL → 图表解读」 |
| 「智慧体育专用」 | 「通用企业问数，Demo 用样例域」 |
| 「对标一切竞品吊打」 | 「对比 Vanna / Chat2DB / SQLBot 的安全与权限差异」 |

---

## 4. 总体里程碑

```text
Week 1          P0  开源准入（License / About / 脱敏检查）
Week 2～4       P1 + P1.5  方案 A Compose Demo + AGENTS.md / make demo-up（AI 可跑）
Week 3～5       P2  README 瘦身 + EN + GIF + Topics
Week 4～6       P3  公开评测报告 + 竞品对比表
Week 5～8       P4  社区模板 + 发文冷启动 +（可选）在线 Demo
Week 8～12      P5  Good First Issues / Release / 节奏运营
```

可与产品线并行：

```text
产品：16 对话门禁 ∥ 03 Phase2
开源：20 本计划（P0～P2 优先，不阻塞产品）
```

---

## 5. P0 · 开源准入（Week 1）

### 5.1 License

| 任务 | 说明 | DoD |
|------|------|-----|
| 选定协议 | **推荐 Apache-2.0**（企业友好、专利条款清晰）；备选 MIT | 决策记录进本计划附录 |
| 新增 `LICENSE` | 根目录标准文本 | 文件存在 |
| 改 README badge | `Proprietary` → `Apache-2.0`（或所选协议） | badge 链接正确 |
| 第三方声明 | 若嵌入字体/图标有约束，写 `NOTICE` 或 README Credits | 无侵权风险 |

### 5.2 GitHub 仓库门面

| 字段 | 建议填写 |
|------|----------|
| Description | `Enterprise NL2SQL · LangGraph · SQL Guard · DataScope · Multi-engine` |
| Homepage | Demo 站点或文档站（暂无可先放 README 锚点 / 后续 HF Space） |
| Topics | `nl2sql` `llm` `fastapi` `vue` `langgraph` `rag` `data-analytics` `sql-security` `opensearch`（按实际） |

### 5.3 脱敏与合规检查清单

开源前必须过一遍：

- [ ] `.env*` / API Key / 内网地址未入库（检查 git history）  
- [ ] 样例数据无真实姓名、手机号、学校敏感信息  
- [ ] 截图中无生产库名、客户 Logo（或已获授权）  
- [ ] 公司专有业务文档是否应留在私有分支（可选：拆 `docs/internal/` 不发布）  
- [ ] `uv.lock` / 依赖无异常私有源  

### 5.4 仓库清理（轻量）

- [ ] 根目录增加 `.github/` 占位（P4 再补全模板）  
- [ ] README 顶部增加「Open Source」状态条（协议 + Demo 链接占位）  
- [ ] 明确 **开源版 vs 公司私有增强** 边界（若有闭源模块，目录隔离）

---

## 6. P1 · 五分钟可跑通 Demo（Week 2～4）

### 6.0 决策钉死：方案 A · 开源治理库 = Compose MySQL 8

**目标**：五分钟跑通、少改代码。对标 SQLBot 的是「一键 Compose + 内置治理库」，**不是**必须换 PostgreSQL。

| 角色 | 开源 / Demo（本计划 · 方案 A） | 公司现网 | 后置（不做进 P1） |
|------|------------------------------|----------|------------------|
| **治理库 `copilot`** | Compose **MySQL 8**；复用现有 `V0xx` + 全部手写 SQL | **MySQL 5.7**（不变） | 治理库切 PG（原方案 B，债务大） |
| **业务问数库** | 多引擎 Catalog；Demo 默认 **excel** Profile | 公司业务库 | — |

> UI「当前问数库」= **业务数据源**。  
> **方案 A 的收益**：`GROUP_CONCAT` / `ON DUPLICATE KEY` / `lastrowid` / ENUM 等 **全部不用动**。

```text
┌──────────────── compose.demo（默认 · 方案 A）──────────┐
│  mysql:8         → 库 `copilot`（治理 · 跑现有 V0xx）   │
│  api + web + zvec volume (+ optional ollama)           │
│  业务样例：demo/profiles/excel/*.xlsx（默认）            │
│  可选：再挂业务侧 mysql/pg/ch 演示多引擎                 │
└────────────────────────────────────────────────────────┘
```

### 6.1 目标体验

```bash
git clone <repo>
cd xb-data-copilot-bot
docker compose -f deploy/docker-compose.demo.yml up -d
# 打开文档端口 → 登录 demo → 点快捷问句
```

陌生人 **不需要** 自备宿主机 MySQL；治理库由 Compose 内 **MySQL 8** 提供，bootstrap 执行现有迁移。无 LLM Key 时走 Fixture。

### 6.2 治理库：方案 A 落地要点（P1 · 窄范围）

| # | 工作项 | 说明 |
|---|--------|------|
| G1 | Compose `mysql:8` | 健康检查；volume 持久化；库名 `copilot` + 用户密码写进 `.env.demo` |
| G2 | 复用迁移 | 启动时跑现有 `scripts/sql/copilot/V*.sql`（或封装 `apply_ddl_to_env_db.py`） |
| G3 | 连接指向容器 | `MYSQL_COPILOT_HOST=mysql`（compose 服务名）；**不改** `copilot_database_url` 驱动形态 |
| G4 | MySQL 5.7 → 8 兼容抽检 | 现网 5.7 SQL 在 8 上烟测（一般兼容）；若个别弃用语法再补丁 |
| G5 | seed | admin / demo 用户 + 可选 DataScope 维度 |
| G6 | 策略不变 | 运行时禁止 DDL / 物理 DELETE；migrate 仅 bootstrap |

**明确不做（P1）**：`COPILOT_DB_DIALECT=postgres`、Alembic 多方言、治理库手写 SQL 方言改造。

### 6.3 业务库 Demo Profile（与治理库方言无关）

| Profile | 业务问数库 | 默认？ | 说明 |
|---------|------------|--------|------|
| **`excel`** | 内置 xlsx → SQLite 镜像 | **是** | 零额外业务库容器 |
| **`mysql`** | 同 Compose MySQL 内再建 `demo_biz`，或独立服务 | 否 | 真 MySQL 方言 + DataScope |
| **`postgres`** | 可选业务侧 PG | 否 | 证明 Catalog 多引擎（**不是**治理库） |
| **`clickhouse`** | 可选 | 否 | OLAP 卖点 |
| `sqlserver` / `oracle` | 文档 + `--dsn` | 否 | 不进默认 compose |

目录约定：

```text
demo/
  profiles/
    _shared/domain.yaml
    _shared/questions.json
    excel/data/shop_pulse.xlsx + seed_meta.json
    mysql/ddl/*.sql + seed_meta.json
    postgres/ddl/*.sql + seed_meta.json   # 业务样例，非治理库
  README.md
```

```bash
python scripts/bootstrap_demo.py --profile excel
# wait mysql:8 → apply V0xx → seed admin
# → excel mirror / 业务 DDL → 默认 datasource → meta/L1 → zvec
```

### 6.4 架构方案（组件级）

| 组件 | Demo 策略 |
|------|-----------|
| **治理库** | Compose **MySQL 8**；bootstrap 跑现有 V0xx + 用户种子 |
| 业务库 | 默认 **excel**；可选 mysql / postgres / … |
| LLM | OpenAI 兼容 → Ollama → **`LLM_MODE=fixture`** |
| Embedding | 预计算种子或首次 rebuild |
| 向量 | Zvec volume |

### 6.5 交付物清单

| ID | 交付物 | 说明 |
|----|--------|------|
| D1 | `deploy/docker-compose.demo.yml` | **`mysql:8`（治理）** + `api` + `web`；业务默认 excel |
| D2 | `scripts/bootstrap_demo.py` | wait MySQL → V0xx → seed → 业务 Profile |
| D3 | `demo/profiles/**` | `_shared` + excel（+ 可选 mysql） |
| D4 | `.env.demo` | 指向 compose 内 MySQL |
| D5 | `docs/DEMO.md` | 方案 A；现网 5.7；PG 后置 |
| D6 | `Makefile`：`demo-up` / `demo-smoke` / `demo-down` | **人和 AI 的唯一入口** |
| D7 | 根目录 `AGENTS.md` | Agent 剧本 + 禁止项（详见 §7） |
| D8 | Fixture 录制包 | 无 Key CI / 默认路径 |

### 6.6 Fixture LLM

- `LLM_MODE=fixture`：预置问句返回业务 Profile 方言下录制结果。  
- CI：`治理=MySQL8` + `业务=excel` + Fixture。

### 6.7 样例域

虚构 **ShopPulse**（或 CampusPulse）：3～5 表、快捷问句 8～12 条；一份 `domain.yaml`，业务 Profile 只换物理 DDL。

### 6.8 明确不做（P1）

| 不做 | 原因 |
|------|------|
| 开源治理库切 PostgreSQL / SQLite | **方案 B**，读写面广，后置 |
| 治理库三选一给用户挑 | 无涨星增益 |
| 继续要求宿主机自备 MySQL 5.7 | 五分钟跑通失败主因 |
| 默认 compose 塞 Oracle/SQL Server | 镜像过重 |
| 改用户生产业务库 | 违反只读策略 |

### 6.9 DoD

- [ ] `docker compose … up -d` 后 **无宿主机 MySQL**，5～10 分钟可登录出结果  
- [ ] 治理库为 Compose **MySQL 8**，volume 持久化，V0xx 幂等/可重复 bootstrap  
- [ ] **未改**治理库手写 SQL 方言（回归：登录、meta CRUD、一次 Fixture 问数）  
- [ ] 默认业务 Profile=`excel`  
- [ ] `demo-smoke` 绿；`DEMO.md` 写明方案 A，并注明「治理库 PG 为后续项」  
- [ ] 根目录存在 **AI 启动指引**（见 §7），Agent 盲测可 up + smoke  

---

## 7. P1.5 · AI Agent 友好启动（与 P1 同迭代）

> **用户诉求**：最好 down 下项目后，**AI 就能很流畅地跑起来**（少问、少猜、少踩坑）。

### 7.1 目标体验（给 Agent 的剧本）

人只说一句：「把这个仓库 Demo 跑起来并问一句样例。」

Agent 应能自动完成，无需再追问宿主机 MySQL / 公司账号：

```text
1. 读 AGENTS.md（或 README「For AI Agents」）
2. 执行唯一入口：make demo-up   （或 scripts/demo_up.sh）
3. 等待 healthy + bootstrap 完成
4. 执行 make demo-smoke         （Fixture 问数，断言 200 + rows）
5. 汇报：UI URL、账号、已通过的样例问句
```

默认路径：**零云端 API Key**（`LLM_MODE=fixture`）。用户若要接真模型，文档单独一节「Bring your own Key」。

### 7.2 为什么现在 Agent 容易卡

| 障碍 | Agent 常见失败 |
|------|----------------|
| 步骤散落 README / 多份 .env | 猜错 `APP_ENV`、连到空主机 |
| 依赖宿主机 MySQL 5.7 | 改 settings、编造连接串 |
| 无单一成功信号 | 以为 up 完就好，实际未 migrate/seed |
| 默认要真 LLM | 无 Key 时反复试 Ollama/云厂商 |
| 无「禁止事项」 | 去改生产口径文档、乱动 Java 参考工程 |

### 7.3 交付物（AI 契约）

| ID | 交付物 | 作用 |
|----|--------|------|
| A1 | 根目录 **`AGENTS.md`** | 给 Coding Agent 的短手册：唯一命令、端口、账号、禁止项、排障 |
| A2 | **`make demo-up`** / `scripts/demo_up.(sh\|ps1)` | 一条命令：compose up + bootstrap + 打印 Ready |
| A3 | **`make demo-smoke`** | 非交互：login → 预置问句 → 断言；失败打明确错误码 |
| A4 | **`make demo-down`** / `demo-reset` | 停栈 / 清 volume 重来（Agent 可自愈） |
| A5 | 默认 `.env.demo` 已齐 | **无必填密钥**；Fixture 开；端口写死文档 |
| A6 | 健康与就绪 | `/health` + `/ready`（含治理库）；bootstrap 写 `.demo/ready` 或日志关键字 `DEMO_READY` |
| A7 | README 双入口 | 人类：Quick Start；Agent：链到 `AGENTS.md`（英文优先短页） |

### 7.4 `AGENTS.md` 必含内容（提纲）

```markdown
# Agent Quickstart
## One command
make demo-up && make demo-smoke

## Defaults
- Governance DB: MySQL 8 in compose (do NOT use host MySQL)
- Business sample: excel profile + Fixture LLM (no API key)
- UI: http://localhost:xxxx  user/pass: ...

## Success criteria
- demo-smoke exit 0
- Log line contains DEMO_READY

## Do not
- Do not point MYSQL_COPILOT_* to the user's production DB
- Do not require cloud LLM for smoke
- Do not edit youplus-base / sport-plantform (if present)

## Troubleshoot
- Port busy → make demo-down / change COMPOSE_PROJECT_NAME
- MySQL not ready → wait healthcheck, re-run bootstrap
- Smoke fail → cat .demo/last-smoke.log
```

### 7.5 设计约束（保证「流畅」）

| 约束 | 说明 |
|------|------|
| **单一真相入口** | Agent 只应依赖 `AGENTS.md` + Makefile，不靠翻 600 行企业 README |
| **幂等** | `demo-up` 重复执行安全；已 seed 则跳过或 upsert |
| **确定性端口** | 文档与 compose 一致；冲突时脚本检测并提示，不静默失败 |
| **失败可诊断** | smoke 失败输出「下一步建议」一行，方便 Agent 自修 |
| **默认 Fixture** | 真 LLM 为可选 overlay（`LLM_MODE=openai` + Key），不挡主路径 |
| **Windows / macOS / Linux** | 提供 `make` 或等价 ps1/sh；CI 与本地命令同源 |

### 7.6 AI 盲测验收（DoD）

- [ ] 新开 Agent 会话，只给仓库路径 +「跑通 Demo」，**不补充口头步骤**  
- [ ] Agent 在 ≤15 分钟内（含拉镜像）完成 `demo-up` + `demo-smoke` 绿  
- [ ] 全程 **无需** 用户提供 API Key / 宿主机 DB 密码  
- [ ] 人为制造一次端口占用后，Agent 能按 `AGENTS.md` 排障恢复  

### 7.7 与 P1 的关系

P1（方案 A Compose）提供「能跑的栈」；P1.5 提供「**人和 AI 都找得到的唯一启动按钮**」。二者同一迭代交付，缺一不可。

---

## 8. P2 · README 与发现入口（Week 3～5）

### 8.1 README 信息架构（前屏 30 秒）

```text
1. 一句话 + 徽章（License / Python / Vue / Stars）
2. Demo GIF（15～25s）或短视频
3. Quick Start（3 条命令）+ 「For AI Agents → AGENTS.md」
4. Why this project（3 点差异化）
5. Features 列表（短）
6. Architecture（折叠或链到 docs）
7. Eval / Security 数字
8. Roadmap + Contributing
9. License
```

长架构图、14 周计划、内部拓扑 → 下沉到 `docs/`，根 README 只链过去。

### 8.2 中英双语文档

| 文件 | 职责 |
|------|------|
| `README.md` | **英文主场**（GitHub 默认） |
| `README.zh-CN.md` | 中文完整版（可由现 README 精炼迁移） |
| `AGENTS.md` | Agent 专用短页（可中英各一节，英文命令为准） |
| 根 README 顶部 | 语言切换 + Agent 入口链接 |

### 8.3 视觉资产

| 资产 | 规格 |
|------|------|
| `docs/images/demo.gif` | ≤ 8MB；展示提问→SSE 进度→表+图 |
| 可选 `docs/images/architecture-simple.svg` | 一页纸架构，去掉内部主机名 |
| 社交媒体封面 | 1280×640，发文用 |

### 8.4 GitHub 发现

- Topics 全开  
- 发布 `v0.1.0-demo` Release（附 compose 包说明）  
- （可选）GitHub Pages / docs 站点后期再做  

### 8.5 DoD

- [ ] 英文 README 可独立读懂并跑通  
- [ ] 中文 README 保留企业向深度链接  
- [ ] About / Topics / License badge 一致  
- [ ] README 显式链到 `AGENTS.md`  

---

## 9. P3 · 可验证评测与对比（Week 4～6）

### 9.1 公开评测报告

基于已有 `docs/eval/` 与 `replay_eval.py`：

| 子集 | 公开指标 | 展示方式 |
|------|----------|----------|
| 开放域问数 | 完成率 / 正确率（人工抽检标准写清） | `docs/eval/REPORT.md` + README 表格 |
| Prompt Injection `inj-*` | **阻断率**（目标 100% 无越权执行） | 安全卖点主数字 |
| DataScope | 越权字面量拒绝用例数 | 简表 |
| 多轮 Memory | 指代消解成功率（可选） | 附录 |

**原则**：方法可复现（命令 + 模型名 + 温度 + 日期）；不夸大；标明 Demo 域 vs 生产域差异。

### 9.2 竞品对比表（README 常驻）

建议对比维度（诚实填写「部分支持 / 需自建」）：

| 维度 | Data Copilot | Vanna | Chat2DB | SQLBot | 其他 |
|------|--------------|-------|---------|--------|------|
| 开源协议 | Apache-2.0? | … | … | … | |
| SQL Guard / AST | ✅ | | | | |
| 行级权限 DataScope | ✅ | | | | |
| 多引擎 Catalog | ✅ | | | | |
| Agent / 多步 SQL | ✅ | | | | |
| 代码知识图谱 | ✅ | | | | |
| 一键 Demo | 目标 ✅ | | | | |

### 9.3 DoD

- [ ] `docs/eval/REPORT.md` 可被第三方按步骤复现  
- [ ] README 嵌入精简对比表 + 链到完整报告  

---

## 10. P4 · 社区与传播（Week 5～8）

### 10.1 社区基建

```text
.github/
  ISSUE_TEMPLATE/
    bug_report.yml
    feature_request.yml
  PULL_REQUEST_TEMPLATE.md
  CONTRIBUTING.md（或根目录）
  CODE_OF_CONDUCT.md（可选）
  workflows/
    demo-smoke.yml      # compose smoke
    backend-pytest.yml  # 已有则对齐
```

### 10.2 Good First Issues（至少 5 个）

示例方向（按仓库实际改）：

1. 英文文案校对 / i18n 缺口  
2. Demo 样例问句增加 3 条  
3. README 徽章与截图更新  
4. 某数据源连接器文档补全  
5. 前端空态 / 无障碍小改进  
6. 评测集增加 2 条 inj 用例  

标签：`good first issue` `documentation` `demo`

### 10.3 传播节奏（冷启动）

| 渠道 | 内容 | 时机 |
|------|------|------|
| 掘金 / 知乎 | 「企业 NL2SQL 如何 Fail-closed」技术长文 + 仓库链接 | Demo 可跑后 |
| 公众号 / 公司技术号 | 架构拆解 + 安全篇 | 同步 |
| Reddit r/MachineLearning / r/LocalLLaMA | 英文短帖 + Demo GIF | EN README 就绪后 |
| Hacker News Show HN | 仅在一键 Demo 真正丝滑时发 | 勿过早 |
| 相关 Awesome 列表 PR | `awesome-nl2sql` 等 | License 明确后 |

**一条铁律**：没有可跑 Demo 前，不大规模发帖（容易一次差评定终身）。

### 10.4 在线 Demo（可选但高杠杆）

| 方案 | 成本 | 说明 |
|------|------|------|
| 自建试用机 + 限流 | 中 | 需防滥用、每日重置样例库 |
| Hugging Face Space | 低～中 | 适合 Fixture + 小模型 |
| 录屏站点 | 低 | 无交互，转化弱于可点 Demo |

最低配：HF Space 跑 Fixture 模式 +「自备 Key 解锁开放域」。

### 10.5 DoD

- [ ] Issue/PR 模板合并  
- [ ] ≥5 个 good first issue 开放  
- [ ] 至少 1 篇中文长文发布；英文帖视精力  
- [ ] （可选）在线 Demo URL 写入 README  

---

## 11. P5 · 持续运营（Week 8～12）

### 11.1 Release 节奏

| 节奏 | 内容 |
|------|------|
| 每月 1 个 minor | 用户可见能力或 Demo 体验改进 |
| 安全修复随时 | Guard / Scope 相关优先发 patch |
| Changelog | `CHANGELOG.md` Keep a Changelog 格式 |

### 11.2 看板指标（每月回顾）

- Stars / Forks / Unique clones  
- Issues 打开→关闭周期  
- Demo smoke  greenery  
- 文档「Quick Start」相关 Issue 数量（越少越好）  

### 11.3 开源版功能边界（建议写进 README）

| 开源包含 | 可保留私有 / 商业 |
|----------|-------------------|
| 问数核心、Guard、DataScope、Catalog、SSE | 客户专属连接器、托管云、专属报表模板 |
| Demo 域与评测脚本 | 真实客户元数据与代码库镜像 |
| MCP / Embed 基础能力 | 企业 SSO / 审计对接定制 |

---

## 12. 任务分解与责任

> 角色可一人多兼；「建议负责人」按职能划分。

### 12.1 P0（约 3～5 人日）

| # | 任务 | 建议负责人 | 产出 |
|---|------|------------|------|
| 0.1 | 协议决策 + `LICENSE` | Owner | 根目录 LICENSE |
| 0.2 | 改 badge / README 协议段 | Docs | PR |
| 0.3 | GitHub About + Topics | Owner | 仓库设置 |
| 0.4 | 脱敏扫描（含历史） | Eng | checklist 勾选 |
| 0.5 | 开源边界说明段落 | Docs | README § |

### 12.2 P1 + P1.5（约 10～14 人日 · 方案 A + AI 入口）

| # | 任务 | 建议负责人 | 产出 |
|---|------|------------|------|
| 1.1 | compose：`mysql:8` 治理 + api/web | Backend | `docker-compose.demo.yml` |
| 1.2 | bootstrap：V0xx + seed admin | Backend | `bootstrap_demo.py` |
| 1.3 | `demo/profiles`：`_shared` + `excel` | Backend | 业务样例 |
| 1.4 | Fixture LLM（默认） | Backend | 无 Key 可 smoke |
| 1.5 | `make demo-up/smoke/down/reset` | Eng | 单一入口 |
| 1.6 | 根目录 `AGENTS.md` | Docs | Agent 契约 |
| 1.7 | `DEMO_READY` / ready 探针 | Backend | 可等待信号 |
| 1.8 | 前端快捷问句 | Frontend | Ask 芯片 |
| 1.9 | AI 盲测一轮 + `docs/DEMO.md` | Eng/Docs | 录像或日志留存 |

### 12.3 P2（约 5～8 人日）

| # | 任务 | 产出 |
|---|------|------|
| 2.1 | README 英文重写 | `README.md` |
| 2.2 | 中文迁移精炼 | `README.zh-CN.md` |
| 2.3 | Demo GIF 录制 | `docs/images/demo.gif` |
| 2.4 | Release v0.1.0-demo | GitHub Release |

### 12.4 P3（约 5～7 人日）

| # | 任务 | 产出 |
|---|------|------|
| 3.1 | 跑评测并固化环境说明 | `docs/eval/REPORT.md` |
| 3.2 | 竞品对比调研填表 | README 表格 |
| 3.3 | 安全数字校准（inj 阻断率） | 报告 + badge 可选 |

### 12.5 P4～P5（持续）

| # | 任务 | 产出 |
|---|------|------|
| 4.1 | `.github` 模板 | 社区基建 |
| 4.2 | Good First Issues | ≥5 |
| 4.3 | 技术长文 | 1+ |
| 4.4 | （可选）在线 Demo | URL |
| 5.1 | 月度 Release + Changelog | 节奏 |

---

## 13. 验收标准（DoD）

### 13.1 P0 完成定义

- [ ] 根目录有开源 `LICENSE`，README 无 Proprietary  
- [ ] GitHub description / topics 非空  
- [ ] 脱敏清单全部勾选  

### 13.2 P1 + P1.5 完成定义

- [ ] 外部同学按文档首次跑通（建议找未接触过项目的人盲测）  
- [ ] Fixture 模式下无 Key 可完成 1 次预置问句  
- [ ] `make demo-up && make demo-smoke` 自动化通过  
- [ ] 存在 `AGENTS.md`；**AI 盲测**（只给仓库路径）能自行跑绿  

### 13.3 增长漏斗完成定义（W8）

```text
发现（Topics/文章）→ 打开 README → 看懂 30 秒 → Clone
  → make demo-up（人或 AI）→ demo-smoke 绿 → Star / Issue / 转发
```

每一环有对应资产（Topics、英文 README、GIF、Demo、`AGENTS.md`、smoke），不允许「只有文章没有可跑仓库」。

---

## 14. 风险与降级

| 风险 | 影响 | 对策 |
|------|------|------|
| 公司未批准开源协议 | P0 阻塞 | 先内部决策；未批前可做 Demo 工程，不改公开 License |
| Demo 太重（GPU/内存） | 跑不通 | Fixture 优先；Ollama 作可选 profile |
| MySQL 8 与现网 5.7 细微差异 | 偶发 SQL | P1 烟测；必要时小补丁，仍保持 MySQL 方言 |
| 后续若再切治理库 PG | 范围回升 | 单独立项（方案 B），不阻塞开源首发 |
| 真实业务信息泄漏 | 合规事故 | P0 脱敏；样例域全新虚构 |
| 过早发帖 Demo 不稳 | 口碑差 | 盲测通过后再传播 |
| 维护精力不足 | Issue 堆积 | 收窄支持范围；标注「best effort」 |
| Agent 乱改配置 / 连生产库 | 事故 | `AGENTS.md` 禁止项；demo 默认只连 compose 网络 |
| 无 `make` 的 Windows 环境 | Agent 卡住 | 提供 `scripts/demo_up.ps1` 与 Makefile 双入口 |

---

## 15. 与现有路线图的关系

| 文档 | 关系 |
|------|------|
| [01-MVP_DEVELOPMENT_PLAN.md](./01-MVP_DEVELOPMENT_PLAN.md) | 已完成基座；开源卖点来自其中的 Guard / Scope / Agent |
| [03-PHASE2_ROADMAP.md](./03-PHASE2_ROADMAP.md) | 产品能力增强；开源 Demo **不依赖** P2-A/B 完成 |
| [16-DIALOGUE_GATE_PLAN.md](./16-DIALOGUE_GATE_PLAN.md) | 体验加分项；可进 Roadmap 对外宣传，但非 P0 |
| [91-PROMPT_SECURITY.md](./91-PROMPT_SECURITY.md) | 公开安全叙事与评测的权威说明 |
| [92-EVAL_QUESTIONS.md](./92-EVAL_QUESTIONS.md) / `eval/` | P3 评测报告原料 |

**推荐并行策略**：

1. 先做本计划 **P0 + P1 + P1.5**（开源准入 + Compose Demo + **AI 可跑**）—— 涨星与「clone 即用」杠杆最大。  
2. 产品侧继续 **16 对话门禁** 与 Phase2。  
3. Demo / Agent 盲测稳定后再 **P2～P4** 发文推星。

---

## 附录 A · 建议排期甘特（示意）

```text
W1  ████ P0 License/About/脱敏
W2  ░░██████ P1 Compose/Seed
W3  ░░░░████████ P1 Fixture + Smoke + AGENTS.md / demo-up
W4  ░░░░░░░░████ AI 盲测收尾 + P2 README 初稿
W5  ░░░░░░░░░░██████ P2 EN/GIF/Release
W6  ░░░░░░░░░░░░████ P3 评测报告
W7  ░░░░░░░░░░░░░░████ P4 模板+Issues+中文长文
W8  ░░░░░░░░░░░░░░░░██ P4 英文传播 / 可选 HF
W9～12 ░░░░░░░░░░░░░░░░▒▒▒▒ P5 月度运营
```

---

## 附录 B · 协议决策备忘（待填）

| 项 | 结论 |
|----|------|
| 选定协议 | ☑ Apache-2.0　□ MIT　□ 其他：______ |
| 决策人 / 日期 | 开源计划落地 v1.5 · 2026-08-12 |
| 是否允许闭源插件目录 | □ 是　□ 否 |
| 商标 / 项目名是否需更名开源 | □ 保持 Data Copilot　□ 更名：______ |

---

## 附录 C · Quick Start 文案草案（落地时贴 README）

```bash
# Humans or AI Agents — preferred
make demo-up && make demo-smoke

# Equivalent
docker compose -f deploy/docker-compose.demo.yml up -d
# bootstrap runs automatically; then open UI (see DEMO.md / AGENTS.md)
```

Ask: *“How many active users last 7 days?”* → table + chart + explanation.

> 开源默认（**方案 A**）：**治理库 = Compose MySQL 8**；**默认 Fixture，无 API Key**。Agent 请先读根目录 `AGENTS.md`。公司现网可继续 MySQL 5.7。治理库切 PostgreSQL 为后续可选项。

---

*维护：每完成一个 P 阶段，在 [02-PROGRESS.md](./02-PROGRESS.md) 增加一行，并更新本文「状态」与附录 B。*
