# Docs 索引 · 开发计划与规范

> **命名约定**：`<序号>-<主题>.md`  
> - `01～09`：总纲 / 进度 / 路线图  
> - `10～19`：产品专项计划（按落地时间排序）  
> - `20～29`：开源运营与增长  
> - `90～99`：规范、评测、集成说明（长期有效）

按文件名排序即可按「总纲 → 专项 → 开源 → 规范」浏览。

---

## 00 · 怎么读

| 你想… | 先看 |
|--------|------|
| 了解 MVP 怎么做出来的 | [01-MVP_DEVELOPMENT_PLAN.md](./01-MVP_DEVELOPMENT_PLAN.md) |
| 看当前完成度 | [02-PROGRESS.md](./02-PROGRESS.md) |
| 看下一阶段产品优先级 | [03-PHASE2_ROADMAP.md](./03-PHASE2_ROADMAP.md) |
| 做开源涨星 / 社区化 | [20-OPENSOURCE_GROWTH_PLAN.md](./20-OPENSOURCE_GROWTH_PLAN.md) |
| 查 DDL / 只读策略 | [90-DATABASE_CHANGE_POLICY.md](./90-DATABASE_CHANGE_POLICY.md) |

---

## 01～09 · 总纲与路线

| 序号 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 01 | [01-MVP_DEVELOPMENT_PLAN.md](./01-MVP_DEVELOPMENT_PLAN.md) | ✅ 已完成 | 14 周 MVP 总纲：架构、权限、LangGraph、API 契约 |
| 02 | [02-PROGRESS.md](./02-PROGRESS.md) | 🔄 持续更新 | 模块完成度、联调清单、下一步 |
| 03 | [03-PHASE2_ROADMAP.md](./03-PHASE2_ROADMAP.md) | ⬜ 进行中 | Phase 2：Chart SSR / 运营闭环 / MCP·iframe |

---

## 10～19 · 产品专项计划

| 序号 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 10 | [10-LLM_DATASOURCE_CONFIG_PLAN.md](./10-LLM_DATASOURCE_CONFIG_PLAN.md) | ✅ | 大模型与业务数据源配置化（一期） |
| 11 | [11-SYSTEM_CONFIG_PROVIDERS_UI_PLAN.md](./11-SYSTEM_CONFIG_PROVIDERS_UI_PLAN.md) | ✅ | 多供应商 × 多引擎 × Catalog UI（二期） |
| 12 | [12-CHART_VISUALIZATION_PLAN.md](./12-CHART_VISUALIZATION_PLAN.md) | ✅ | Ask 图表：chartSpec + 前端 AntV |
| 13 | [13-ASK_STREAM_UI_PLAN.md](./13-ASK_STREAM_UI_PLAN.md) | ✅ | 问数 SSE 流式界面与时间线 |
| 14 | [14-BRIEF_REPORT_PLAN.md](./14-BRIEF_REPORT_PLAN.md) | ✅ | 报告分析（Brief Report · A4 PDF） |
| 15 | [15-DEEP_ANALYTICS_REPORT_PLAN.md](./15-DEEP_ANALYTICS_REPORT_PLAN.md) | ⏸ 暂缓 | 深度分析报告（Insight Engine / DAR） |
| 16 | [16-DIALOGUE_GATE_PLAN.md](./16-DIALOGUE_GATE_PLAN.md) | ⬜ 待做 | 对话门禁与多轮澄清（AskUserQuestion） |

**建议实施顺序（未完成项）**：

```text
16 对话门禁  →  03 Phase2（P2-A SSR ∥ P2-B 运营闭环）  →  P2-C 嵌入/MCP
                                    ↘ 20 开源增长（可并行）
```

---

## 20～29 · 开源与增长

| 序号 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 20 | [20-OPENSOURCE_GROWTH_PLAN.md](./20-OPENSOURCE_GROWTH_PLAN.md) | 🟡 P0～P1.5 已交付 | 开源涨星：方案 A Demo、AGENTS.md；P2～P5 待做 |

---

## 90～99 · 规范与集成

| 序号 | 文件 | 说明 |
|------|------|------|
| 90 | [90-DATABASE_CHANGE_POLICY.md](./90-DATABASE_CHANGE_POLICY.md) | 业务库只读 / 问数库 DDL 变更策略 |
| 91 | [91-PROMPT_SECURITY.md](./91-PROMPT_SECURITY.md) | Prompt Injection 威胁模型与运营规范 |
| 92 | [92-EVAL_QUESTIONS.md](./92-EVAL_QUESTIONS.md) | 评测问句说明（含 inj-*） |
| 93 | [93-EMBED.md](./93-EMBED.md) | iframe 嵌入问数集成说明 |
| 94 | [94-MCP.md](./94-MCP.md) | MCP Server 配置与工具列表 |

### 其它目录

| 路径 | 说明 |
|------|------|
| [eval/](./eval/) | 评测 JSON（agent / memory / injection / research） |
| [images/](./images/) | README / 产品截图 |

---

## 重命名对照（旧 → 新）

| 旧文件名 | 新文件名 |
|----------|----------|
| `DEVELOPMENT_PLAN.md` | `01-MVP_DEVELOPMENT_PLAN.md` |
| `PROGRESS.md` | `02-PROGRESS.md` |
| `PHASE2_ROADMAP.md` | `03-PHASE2_ROADMAP.md` |
| `LLM_DATASOURCE_CONFIG_PLAN.md` | `10-LLM_DATASOURCE_CONFIG_PLAN.md` |
| `SYSTEM_CONFIG_PROVIDERS_UI_PLAN.md` | `11-SYSTEM_CONFIG_PROVIDERS_UI_PLAN.md` |
| `CHART_VISUALIZATION_PLAN.md` | `12-CHART_VISUALIZATION_PLAN.md` |
| `ASK_STREAM_UI_PLAN.md` | `13-ASK_STREAM_UI_PLAN.md` |
| `BRIEF_REPORT_PLAN.md` | `14-BRIEF_REPORT_PLAN.md` |
| `DEEP_ANALYTICS_REPORT_PLAN.md` | `15-DEEP_ANALYTICS_REPORT_PLAN.md` |
| `DIALOGUE_GATE_PLAN.md` | `16-DIALOGUE_GATE_PLAN.md` |
| `DATABASE_CHANGE_POLICY.md` | `90-DATABASE_CHANGE_POLICY.md` |
| `PROMPT_SECURITY.md` | `91-PROMPT_SECURITY.md` |
| `EVAL_QUESTIONS.md` | `92-EVAL_QUESTIONS.md` |
| `EMBED.md` | `93-EMBED.md` |
| `MCP.md` | `94-MCP.md` |
| — | `20-OPENSOURCE_GROWTH_PLAN.md`（新增） |

---

*维护：新增专项计划时按空号取序号；完成后在 [02-PROGRESS.md](./02-PROGRESS.md) 勾选，并更新本表「状态」列。*
