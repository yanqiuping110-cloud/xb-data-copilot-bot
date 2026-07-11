# Phase 2 产品路线图 · Chart SSR / 运营闭环 / 对外集成

> **状态**：已纳入开发计划（2026-07）  
> **版本**：v1.0  
> **定位**：MVP（14 周）完成后的 **Phase 2 三大优先级**，借鉴 [SQLBot](https://github.com/dataease/SQLBot) 的产品化思路，**不替代**现有 LangGraph / SQL Guard / DataScope 企业底座。  
> **关联文档**：[DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) §14、[CHART_VISUALIZATION_PLAN.md](./CHART_VISUALIZATION_PLAN.md)、[DEEP_ANALYTICS_REPORT_PLAN.md](./DEEP_ANALYTICS_REPORT_PLAN.md)

---

## 目录

1. [总览与排期](#1-总览与排期)
2. [P2-A · Chart SSR 统一渲染](#2-p2-a--chart-ssr-统一渲染)
3. [P2-B · Badcase → L1/术语 运营闭环](#2-p2-b--badcase--l1术语-运营闭环)
4. [P2-C · MCP / iframe 对外集成](#2-p2-c--mcp--iframe-对外集成)
5. [里程碑与验收](#5-里程碑与验收)
6. [风险与依赖](#6-风险与依赖)

---

## 1. 总览与排期

| 代号 | 主题 | 借鉴 SQLBot | 周期（估） | 依赖 |
|------|------|-------------|------------|------|
| **P2-A** | Chart SSR 统一渲染 | `g2-ssr` 服务端出图 | 2～3 周 | Node 侧车或独立进程；现有 `ChartSpec` |
| **P2-B** | 越问越准运营闭环 | 术语库 + SQL 样例 + Prompt 运营 | 2～3 周 | 已有 `badcase_l1`、`copilot_sql_example` |
| **P2-C** | MCP / iframe 嵌入 | Web 嵌入、MCP、弹窗 | 2 周 | JWT / embed token；CORS |

**建议实施顺序**：P2-A 与 P2-B 可并行（前后端分工）；P2-C 在 P2-A 图表稳定后接入 MCP「带图问数」体验更佳。

```text
Phase 2（约 6～8 周）
├─ W1～W3  P2-A  Chart SSR（Ask + Insight PDF 共用）
├─ W1～W3  P2-B  术语库 + badcase 审核台（与 P2-A 并行）
└─ W4～W5  P2-C  embed 页 + MCP Server
└─ W6       联调、演示包、文档
```

---

## 2. P2-A · Chart SSR 统一渲染

### 2.1 背景

| 现状 | 问题 |
|------|------|
| Ask 前端 | `ChartSpec` + 前端组件渲染（已实现，见 [CHART_VISUALIZATION_PLAN.md](./CHART_VISUALIZATION_PLAN.md)） |
| Insight PDF | `matplotlib` → PNG（`chart_png.py`），中文缺字、样式与在线不一致 |
| 深度报告 | 在线内联图仅为 CSS 占位，与 PDF 脱节 |

SQLBot 通过 **`g2-ssr`** 在服务端用 AntV G2 渲染，保证导出与预览一致。我们采用 **「ChartSpec 为唯一真相 + SSR 服务出 PNG/SVG」**，不推翻现有规则引擎。

### 2.2 目标

1. **单一渲染链路**：`ChartSpec` → SSR → `{ pngPath | svgPath }`  
2. **三处消费**：Ask.vue（可选 SSR 缩略图或仍用客户端 G2）、Insight 在线预览、Insight PDF / 长报告  
3. **中文与主题**：统一字体（Noto Sans SC / 系统 fallback）、与 `research_pdf_theme` 配色一致  
4. **Fail-open**：SSR 失败时降级现有 matplotlib 或仅表格，问数/报告不中断  

### 2.3 架构

```text
                    ┌─────────────────┐
  LangGraph         │  build_chart    │
  chartSpec ───────►│  (已有)         │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ chart_ssr_client │  HTTP/gRPC
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │  chart-ssr 服务（Node）      │
              │  · @antv/g2 + g2-ssr 思路   │
              │  · 输入 ChartSpec JSON      │
              │  · 输出 PNG/SVG + 宽高      │
              └──────────────┬──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    Ask.vue            Insight Section      export_pdf /
    (img/cache)        InlineChart           report_long.html
```

### 2.4 实施步骤

| 步骤 | 内容 | 产出 |
|------|------|------|
| A1 | 新建 `chart-ssr/`（或 `g2-ssr/`）Node 服务：`POST /render` `{ chartSpec, width, height, format }` | Docker 镜像 + README |
| A2 | Python `app/chart/ssr_client.py`：超时、缓存（trace_id + spec hash）、降级 | 单测 mock |
| A3 | 替换 `research/chart_png.py` 优先走 SSR；保留 matplotlib fallback | Insight PDF 验收 |
| A4 | Ask 流：`chart_ready` SSE 可带 `chartImageUrl`（可选） | 演示一致 |
| A5 | 配置项：`CHART_SSR_ENABLED`、`CHART_SSR_URL`、`CHART_SSR_TIMEOUT_MS` | `.env.example` |
| A6 | 评测：固定 ChartSpec 集快照对比（像素 hash 或人工） | `tests/test_chart_ssr.py` |

### 2.5 验收标准（DoD）

- [ ] 同一 `ChartSpec` 在 Ask 与 Insight PDF 中**视觉一致**（允许分辨率差，不允许柱形/标签语义差）  
- [ ] 中文轴标签、图例无 tofu（□）  
- [ ] SSR 宕机时 Ask 仍返回表格 + answer；Insight 仍生成 PDF（无图或 fallback 图）  
- [ ] P99 渲染 < 3s（单图，1080p 宽）  

---

## 3. P2-B · Badcase → L1/术语 运营闭环

### 3.1 背景

| 已有能力 | 缺口 |
|----------|------|
| `copilot_ask_turn.is_badcase`、用户 down 反馈 | 缺「术语库」独立实体与召回注入 |
| `build_l1_draft_from_badcase`（`badcase_l1.py`） | 一键沉淀有草稿，缺**审核发布工作流** |
| Admin meta 页 L1 / badcase 列表 | 缺 SQLBot 式「术语 ⇄ 字段/指标」映射 UI |
| L1 软参考注入 Plan/Prompt | 缺发布后**命中率**与**效果对比**看板 |

SQLBot 强调 **自定义 Prompt、术语库、SQL 示例** 三件套实现「越问越准」。我们在 **不降低 SQL Guard 硬约束** 前提下，把运营能力产品化。

### 3.2 目标

1. **术语库（Glossary）**：业务别名 → 标准字段/指标/口径说明，参与召回与 Prompt  
2. **Badcase 一键沉淀**：问数页/Trace → 生成 L1 草稿 + 可选术语建议 → 运营审核 → 发布  
3. **闭环可度量**：发布后同类问句 L1 命中率、LLM 调用率、用户满意度（up/down）趋势  

### 3.3 数据模型（新增 DDL 草案）

```sql
-- V013__glossary_and_l1_workflow.sql（草案）

CREATE TABLE copilot_glossary_term (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  term VARCHAR(128) NOT NULL COMMENT '业务术语/别名',
  canonical_name VARCHAR(256) NOT NULL COMMENT '标准指标或字段表述',
  definition TEXT COMMENT '口径说明',
  ref_type ENUM('metric','column','table','concept') NOT NULL DEFAULT 'concept',
  ref_id BIGINT NULL COMMENT '关联 copilot_metric_definition.id 等',
  scope_role VARCHAR(32) NULL COMMENT 'ADMIN/OPERATOR/SCHOOL，空=全局',
  status TINYINT NOT NULL DEFAULT 0 COMMENT '0草稿 1已发布 2停用',
  created_by BIGINT,
  created_at DATETIME,
  updated_at DATETIME,
  deleted TINYINT NOT NULL DEFAULT 0,
  UNIQUE KEY uk_term_scope (term, scope_role, deleted)
) COMMENT '术语库';

ALTER TABLE copilot_sql_example
  ADD COLUMN source_trace_id VARCHAR(64) NULL COMMENT '来自 badcase 沉淀',
  ADD COLUMN review_status TINYINT NOT NULL DEFAULT 0 COMMENT '0草稿 1已发布',
  ADD COLUMN reviewed_by BIGINT NULL,
  ADD COLUMN reviewed_at DATETIME NULL;
```

术语写入 **Zvec/ES 索引**（与 metric 同级或独立 collection `copilot_glossary`）。

### 3.4 API 与管理端

| API | 说明 |
|-----|------|
| `GET/POST/PUT /admin/meta/glossary` | 术语 CRUD + 发布 |
| `POST /admin/meta/badcase/{traceId}/promote-l1` | 一键生成 L1 草稿（已有逻辑封装） |
| `POST /admin/meta/badcase/{traceId}/promote-glossary` | 从问句抽取术语候选 |
| `POST /admin/meta/l1/{id}/publish` | 草稿 → 发布，触发 reindex |
| `GET /admin/meta/ops/stats` | 命中率、badcase 数、发布数（7/30 天） |

**前端**（`AdminMeta` 或独立「运营中心」Tab）：

- Badcase 队列：问句、SQL、反馈、**一键沉淀**、编辑、发布  
- 术语库：表格 + 关联指标/字段 picker  
- L1 样例：草稿/已发布筛选，来源 trace 链接  

### 3.5 召回与 Prompt 注入

| 触点 | 行为 |
|------|------|
| `extract_keywords` 后 | 术语表 FTS/向量 match → 追加 `【术语对齐】` 块 |
| `build_llm_context` | 已发布术语 top-K 注入（定界符内，经 `sanitize_recall_text`） |
| L1 硬匹配 | 不变；发布时 `review_status=1` 且 `draft=false` |

### 3.6 实施步骤

| 步骤 | 内容 |
|------|------|
| B1 | DDL V013 + `MetaRepository` glossary CRUD |
| B2 | 术语索引 build/rebuild（复用 `MetaKnowledgeService` 模式） |
| B3 | 召回链注入 glossary 块 + 单测 |
| B4 | Admin API promote/publish + 权限 `require_meta_manager` |
| B5 | 前端运营台：badcase 队列 + 术语 + L1 发布流 |
| B6 | `replay_eval` 子集 `ops-before-after`：发布前后命中率对比 |

### 3.7 验收标准（DoD）

- [ ] 运营从 badcase 列表 **≤3 次点击** 完成 L1 发布  
- [ ] 术语发布后，含该别名的评测问句 **召回上下文出现 canonical_name**  
- [ ] 已发布 L1 参与硬匹配，草稿不参与  
- [ ] Admin 可看 7 日 badcase 数、发布数、L1 命中次数（只读统计）  

---

## 4. P2-C · MCP / iframe 对外集成

### 4.1 背景

SQLBot 支持 **Web 嵌入、弹窗嵌入、MCP**，便于接入 n8n、Dify、MaxKB、DataEase。我们当前仅自有 Vue 控制台，业务系统需跳转全站。

### 4.2 目标

| 形态 | 场景 |
|------|------|
| **iframe 嵌入页** | 体育后台 / 运营 BI 内嵌问数面板 |
| **弹窗 SDK** | `DataCopilot.open({ token, question })` 轻量脚本 |
| **MCP Server** | Cursor / Agent 工具调用问数与深度报告 |

### 4.3 安全模型

| 机制 | 说明 |
|------|------|
| **Embed Token** | 短期 JWT 或 `copilot_embed_token`（appId + secret 换 token，scoped user/role） |
| **allowlist 域名** | `EMBED_ALLOWED_ORIGINS` postMessage 校验 |
| **能力范围** | embed 模式默认禁用 `/admin`；仅 `/ask` + 可选只读 history |
| **CORS** | 嵌入页与 API 分离域名时的白名单 |

### 4.4 交付物

#### 4.4.1 iframe 嵌入

| 路径 | 说明 |
|------|------|
| `frontend/src/views/EmbedAsk.vue` | 精简 Ask UI（无侧栏 admin） |
| `/embed/ask?token=...` | 路由 + `X-Frame-Options` / CSP `frame-ancestors` 可配置 |
| `docs/EMBED.md` | 集成说明、示例 iframe 代码 |

#### 4.4.2 MCP Server

| 工具名 | 参数 | 返回 |
|--------|------|------|
| `copilot_ask` | `question`, `sessionId?` | `{ answer, columns, rows, chartSpec?, traceId }` |
| `copilot_research` | `requestText`, `templateCode?` | `{ reportId, status, pdfUrl? }`（异步可轮询） |
| `copilot_list_sessions` | — | 最近 session 列表 |

实现选项（二选一，优先 A）：

- **A**：`backend/app/mcp/` FastMCP / stdio，与 uvicorn 同 repo  
- **B**：独立 `mcp-server/` 包，HTTP 调现有 REST  

配置：`MCP_ENABLED`、`MCP_API_KEY`（与 embed 共用或分离）。

#### 4.4.3 弹窗 SDK（可选，Phase 2.1）

`frontend/public/copilot-embed.js`：加载 iframe overlay + postMessage 桥。

### 4.5 实施步骤

| 步骤 | 内容 |
|------|------|
| C1 | Embed token 签发 API `POST /api/v1/embed/token`（ADMIN 或 appId/secret） |
| C2 | `EmbedAsk.vue` + 路由 + 样式隔离 |
| C3 | CSP / `frame-ancestors` 配置项 |
| C4 | MCP Server 注册 `copilot_ask`（读-only 问数） |
| C5 | MCP `copilot_research`（流式可选简化） |
| C6 | `docs/EMBED.md` + `docs/MCP.md` + README 链接 |

### 4.6 验收标准（DoD）

- [ ] 第三方页面 iframe 嵌入后可完成一次问数（表格 + 回答）  
- [ ] 非法 origin postMessage 被拒绝  
- [ ] Cursor MCP 配置示例可调用 `copilot_ask` 并返回结构化结果  
- [ ] Embed token 过期后 401，不泄露 admin 能力  

---

## 5. 里程碑与验收

| 里程碑 | 包含 | 目标日期（相对 Phase 2 起点） |
|--------|------|-------------------------------|
| **M2.1** | P2-A SSR 服务 + Insight PDF 走 SSR | +3 周 |
| **M2.2** | P2-B 术语库 + badcase 发布台 | +3 周 |
| **M2.3** | P2-C iframe + MCP ask | +5 周 |
| **M2.4** | 演示包：Docker Compose 含 chart-ssr；embed 示例 HTML | +6 周 |

**Phase 2 总体验收**：

1. 演示脚本：嵌入页问数 → 出 SSR 图 → badcase 沉淀 → 同问句 L1 命中  
2. `replay_eval` 新增子集 `chart-ssr`、`ops-loop`（各 ≥5 条）  
3. 文档齐全：`PHASE2_ROADMAP.md`、`EMBED.md`、`MCP.md` 与 `.env.example` 同步  

---

## 6. 风险与依赖

| 风险 | 缓解 |
|------|------|
| Node SSR 增加部署复杂度 | Docker 侧车 + `CHART_SSR_ENABLED=false` 全降级 |
| 术语/L1 错误发布导致误匹配 | 草稿→审核→发布；发布可回滚 `status=2` |
| Embed token 泄露 | 短 TTL + origin 绑定 + 只读 scope |
| MCP 滥用问数 | API Key + 速率限制继承 `ASK_RATE_LIMIT` |
| SQLBot 代码许可证 | **仅借鉴思路**，不直接拷贝 SQLBot 源码（FIT2CLOUD / GPL 限制） |

---

## 附录 A · 配置项预览（Phase 2 新增）

```bash
# Chart SSR
CHART_SSR_ENABLED=false
CHART_SSR_URL=http://127.0.0.1:3001
CHART_SSR_TIMEOUT_MS=5000

# 术语库
GLOSSARY_RECALL_ENABLED=true
GLOSSARY_RECALL_TOP_K=5

# Embed / MCP
EMBED_ENABLED=false
EMBED_ALLOWED_ORIGINS=https://your-portal.example.com
EMBED_TOKEN_TTL_SEC=3600
MCP_ENABLED=false
MCP_API_KEY=
```

---

**维护**：子项开工时在 [PROGRESS.md](./PROGRESS.md) 登记；完成后更新 [CHART_VISUALIZATION_PLAN.md](./CHART_VISUALIZATION_PLAN.md) §SSR 与本文里程碑勾选。
