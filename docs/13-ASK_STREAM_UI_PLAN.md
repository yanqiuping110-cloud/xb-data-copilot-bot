# 问数流式界面优化 · 前端体验方案

> **状态**：Phase 0–2 已落地（2026-07-11）  
> **版本**：v1.0 · 2026-07  
> **范围**：`POST /api/v1/ask` 流式问数（SSE）的前端布局重组 + 后端进度事件增强  
> **原则**：复用 Insight Engine 已有流水线组件；思考过程 **仅 ADMIN 可见**（防泄露表名/字段名）  
> **非目标**：Insight Engine（DAR）报告页改造（见 [15-DEEP_ANALYTICS_REPORT_PLAN.md](./15-DEEP_ANALYTICS_REPORT_PLAN.md)）

---

## 目录

1. [背景与现状](#1-背景与现状)
2. [优化目标](#2-优化目标)
3. [安全与权限（思考过程 · ADMIN only）](#3-安全与权限思考过程--admin-only)
4. [布局重组](#4-布局重组)
5. [后端 SSE 增强](#5-后端-sse-增强)
6. [前端组件设计](#6-前端组件设计)
7. [数据流与状态模型](#7-数据流与状态模型)
8. [分步实施指南](#8-分步实施指南)
9. [配置项](#9-配置项)
10. [验收标准](#10-验收标准)
11. [风险与降级](#11-风险与降级)

---

## 1. 背景与现状

### 1.1 当前界面问题

| 区域 | 现状 | 问题 |
|------|------|------|
| 思考过程 | `details` + `<pre>` 展示 `thinking_delta` 全文 | 暴露真实表名、列名、SQL 片段；所有登录用户均可见 |
| 流水线步骤 | `Ask.vue` 内 `<ul class="progress-list">` 纯文字列表 | 20+ 节点纵向堆叠，无图标/耗时/副文案，「不酷炫」 |
| 回答正文 | `msg.text` 与步骤列表、SQL、图表混排 | 信息层次不清，完成后仍占大量纵向空间 |
| SSE 消费 | `onProgress` 仅用 `label`，忽略 `node` / `detail` | 后端已推送召回数量、关键词等，前端未展示 |

### 1.2 已有可复用资产

| 资产 | 路径 | 说明 |
|------|------|------|
| 6 步宏观流水线 | `frontend/src/utils/pipelineMapper.js` | `理解 → 召回 → 规划 → SQL → 执行 → 回答` |
| 流水线条 | `frontend/src/components/insight/PipelineStrip.vue` | 圆点 + done/active 样式 |
| 活动 Feed | `frontend/src/components/insight/ActivityFeed.vue` | 滚动日志列表 |
| 状态行 | `frontend/src/components/insight/StatusLine.vue` | 单行当前状态 |
| 节点中文标签 | `backend/app/agent/log_utils.py` · `NODE_LABELS` | 与 SSE `progress.label` 一致 |
| 进度 detail | `backend/app/agent/runner.py` · `_progress_detail()` | 关键词、召回 count、rowCount 等 |
| ADMIN 门控先例 | `Ask.vue` · `canShowSqlInChat` | `user.role === 'ADMIN'` 才展示 SQL |

### 1.3 后端已支持的 SSE 事件（问数）

| 事件 | 载荷 | 前端是否消费 |
|------|------|-------------|
| `progress` | `{ node, label, detail? }` | 部分（仅 label） |
| `thinking_delta` | `{ delta }` | 是（需改为 ADMIN only） |
| `text_delta` | `{ delta }` | 是 |
| `done` | `AskResponse` | 是 |
| `error` | `{ code, message }` | 是 |

---

## 2. 优化目标

1. **宏观 + 微观双层进度**：顶栏 6 步 Pipeline Strip；详情区可折叠时间线。
2. **进度「酷炫」**：图标、动画、副文案（从 `detail` / 新字段 `summary` 生成）、耗时。
3. **布局重组**：进行中只看「状态条 + 当前一步 + 流式回答」；完成后默认折叠执行详情。
4. **思考过程 ADMIN only**：前后端双重门控，普通用户不接收、不展示、不落库到会话回放。
5. **后端 SSE 增强**：统一 `progress` 结构，可选 `activity` 事件，减少前端硬编码。

---

## 3. 安全与权限（思考过程 · ADMIN only）

### 3.1 威胁说明

DeepSeek 思考模式输出的 `reasoning_content` 常包含：

- 候选表名（如 `sport_activity_qzs_time`）
- 字段名（`record_date`、`user_id`）
- SQL 草稿与校验逻辑

对 **SCHOOL / OPERATOR** 用户属于元数据泄露，与「聊天界面不展示 SQL」策略一致，思考过程应等同敏感调试信息。

### 3.2 权限矩阵

| 内容 | ADMIN | OPERATOR | SCHOOL |
|------|-------|----------|--------|
| 宏观 6 步 Pipeline | ✓ | ✓ | ✓ |
| 微观节点时间线（无表名） | ✓ | ✓ | ✓ |
| 思考过程面板 | ✓ | ✗ | ✗ |
| SQL 文本 | ✓ | ✗ | ✗ |
| 图表 + 表格 + 自然语言回答 | ✓ | ✓ | ✓ |

### 3.3 后端门控（必须）

**禁止仅靠前端隐藏**——须在 SSE 源头的 `stream_ask_graph` 根据 `ctx.role` 决定是否推送 `thinking_delta`。

```python
# runner.py · _prepare_ask_run 建议逻辑
thinking_delta_queue = None
if (
    stream
    and settings.llm_thinking_enabled
    and settings.llm_thinking_stream
    and ctx.role == UserRole.ADMIN  # 新增
):
    thinking_delta_queue = asyncio.Queue()
```

| 项 | 行为 |
|----|------|
| 非 ADMIN | 不创建 `thinking_delta_queue`；LLM 仍可思考，但不向 SSE 推送 |
| `FORMAT_ANSWER` 等节点的 `thinking_queue` | 同样仅在 ADMIN 流式会话注入 |
| 历史回放 | `result_json` **不存** `thinking`；`GET /sessions/.../messages` 不返回该字段 |
| Trace 审计 | 可选：完整 `reasoning` 仅写 `copilot_ask_span` 供 ADMIN 在运营后台查看（Phase 2） |

### 3.4 前端门控（必须）

```javascript
// Ask.vue
const canShowThinking = computed(() => user.value?.role === 'ADMIN')

// onThinkingDelta：非 ADMIN 不注册回调（或回调内直接 return）
// 模板：<details v-if="canShowThinking && msg.thinking" ...>
```

与现有 `canShowSqlInChat` 并列，命名建议：`canShowThinkingProcess`。

### 3.5 配置项

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_THINKING_STREAM_ADMIN_ONLY` | `true` | 为 `true` 时仅 ADMIN 接收 `thinking_delta` |
| `LLM_THINKING_ENABLED` | 按环境 | 与角色无关；思考仍参与推理，只是不对非 ADMIN 暴露 |

---

## 4. 布局重组

### 4.1 目标线框（Ask 助手消息卡片）

```text
┌─────────────────────────────────────────────────────────┐
│ [Pipeline Strip]  理解 ✓  召回 ✓  规划 ●  SQL ○ …     │  ← 宏观 6 步，始终可见
├─────────────────────────────────────────────────────────┤
│ [StatusLine]  ⟳ 正在生成 SQL…                           │  ← 仅进行中显示
├─────────────────────────────────────────────────────────┤
│ ▶ 思考过程（仅 ADMIN · 可折叠 · 默认收起）               │  ← 有内容才显示
├─────────────────────────────────────────────────────────┤
│ 【回答正文】流式 / 最终摘要                              │  ← 主内容区
├─────────────────────────────────────────────────────────┤
│ ▶ 执行详情（完成后默认折叠）                             │
│   └─ [AskTimeline] 微观节点 + 图标 + 副文案 + 耗时       │
├─────────────────────────────────────────────────────────┤
│ [ResultPanel] 图表 + 表格                                │
├─────────────────────────────────────────────────────────┤
│ SQL（仅 ADMIN）                                          │
└─────────────────────────────────────────────────────────┘
```

### 4.2 进行中 vs 完成后

| 状态 | 默认展示 | 折叠 |
|------|----------|------|
| `loading === true` | Pipeline Strip + StatusLine + 流式回答 | 执行详情展开（可选，最多显示最近 5 步） |
| `loading === false` | 回答 + 图表表格 | 执行详情、思考过程默认 **收起** |
| 错误 | 错误文案 + 已执行步骤 | 思考过程仍 ADMIN only |

### 4.3 与现有元素迁移

| 现位置 | 迁移后 |
|--------|--------|
| `progress-list` 纯列表 | 收入「执行详情」折叠区 · `AskTimeline` |
| `thinking-panel` 置顶 open | ADMIN only + 默认 `closed` + 仍在回答上方 |
| `answer-line` | 保持在 Pipeline 下方、执行详情上方 |
| `ResultPanel` | 保持在回答之后 |

---

## 5. 后端 SSE 增强

### 5.1 `progress` 事件扩展（推荐 v2 载荷）

在现有 `node` / `label` / `detail` 基础上增加结构化字段，减少前端拼接逻辑：

```json
{
  "node": "do_recall_tables",
  "label": "召回相关表",
  "phase": "recall",
  "phaseLabel": "召回",
  "status": "done",
  "durationMs": 142,
  "summary": "命中 3 张候选表",
  "icon": "table",
  "detail": { "count": 3 }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `phase` | string | `understand` \| `recall` \| `plan` \| `sql` \| `execute` \| `answer` |
| `phaseLabel` | string | 中文阶段名，与 `PIPELINE_STEPS` 对齐 |
| `status` | string | `running` \| `done` \| `fail` \| `skipped` |
| `durationMs` | int? | 节点耗时（从 span 写入点读取） |
| `summary` | string? | **脱敏**人话摘要，禁止含物理表名/列名 |
| `icon` | string? | 前端图标 key，如 `memory`、`search`、`code` |
| `detail` | object? | 保留现有结构，供 ADMIN 调试或副文案生成 |

**`summary` 脱敏规则（后端生成）**

| 节点 | 推荐 summary | 禁止 |
|------|--------------|------|
| `extract_keywords` | `关键词：活动、月份、折线图` | — |
| `do_recall_tables` | `命中 3 张候选表` | 不出现 `sport_*` 表名 |
| `execute_sql` | `返回 12 行` | — |
| `plan_question` | `复杂度 medium · 2 步` | — |
| `generate_sql` | `SQL 已生成` | 不输出 SQL 片段 |

实现位置建议：

- `backend/app/agent/streaming.py` · `progress_event()` 增加参数
- `backend/app/agent/runner.py` · `_progress_detail()` 扩展为 `_progress_payload()`
- `backend/app/agent/log_utils.py` · 新增 `node_to_phase()`（或复用前端 `pipelineMapper` 的镜像）

### 5.2 新增 `activity` 事件（可选 · P1）

与 Insight Engine 对齐，用于「活动日志」滚动区：

```json
{
  "level": "info",
  "message": "召回阶段完成，进入问句规划",
  "phase": "recall",
  "ts": 1710000000000
}
```

触发点：阶段切换、Agent 选工具、验证失败重试等。

### 5.3 新增 `phase_change` 事件（可选 · P2）

```json
{
  "phase": "sql",
  "phaseLabel": "SQL",
  "step": 4,
  "total": 6
}
```

Pipeline Strip 可直接消费，无需从 `progress.node` 推导。

### 5.4 `thinking_delta` 行为变更

| 角色 | 服务端行为 |
|------|------------|
| ADMIN | 照常推送 `thinking_delta` |
| 非 ADMIN | **不推送**；节点仍正常 `progress` |

### 5.5 事件时序（目标）

```text
progress(理解…) → progress(召回…) → … 
  ↳ thinking_delta*（仅 ADMIN，可与 progress 交错）
  ↳ text_delta*（回答流式）
activity（可选）
done（AskResponse）
```

---

## 6. 前端组件设计

### 6.1 新增组件

| 组件 | 路径 | 职责 |
|------|------|------|
| `AskPipelineHeader.vue` | `frontend/src/components/ask/` | 封装 `PipelineStrip` + `StatusLine` |
| `AskTimeline.vue` | 同上 | 微观节点时间线（图标、副文案、耗时、状态动画） |
| `AskThinkingPanel.vue` | 同上 | ADMIN only 思考过程；默认折叠；样式与 Insight 区分 |

### 6.2 `AskTimeline` 单步 UI

```text
[✓] 召回相关表          142ms
    命中 3 张候选表
```

| 状态 | 视觉 |
|------|------|
| `running` | 左侧 `Loading` 旋转 +  indigo 高亮条 |
| `done` | 绿色 ✓ + 副文案灰色小字 |
| `fail` | 红色 ! + 错误提示 |
| `skipped` | 灰色 − |

图标映射（`icon` → Element Plus Icon）：

| icon | 节点示例 |
|------|----------|
| `edit` | 清洗问句 |
| `collection` | 加载记忆/偏好 |
| `search` | 召回类 |
| `cpu` | 规划 / Agent |
| `document` | 生成 SQL |
| `video-play` | 执行查询 |
| `chat-line-round` | 生成回答 |
| `trend-charts` | 生成图表 |

### 6.3 `formatStepSubtitle(node, detail, summary)` 

优先使用后端 `summary`；否则前端 fallback：

```javascript
export function formatStepSubtitle(evt) {
  if (evt.summary) return evt.summary
  const d = evt.detail || {}
  if (d.keywords?.length) return `关键词：${d.keywords.join('、')}`
  if (d.count != null) return `命中 ${d.count} 项`
  if (d.rowCount != null) return `${d.rowCount} 行`
  if (d.complexity) return `复杂度 ${d.complexity}`
  return ''
}
```

### 6.4 扩展 `pipelineMapper.js`

增加与后端一致的 `phase` 常量：

```javascript
export const PIPELINE_PHASES = [
  { key: 'understand', label: '理解', step: 1 },
  { key: 'recall', label: '召回', step: 2 },
  // ...
]
export function nodeToPhase(node) { /* 与后端 mirror */ }
```

### 6.5 `ask.js` SSE 分发扩展

```javascript
// 新增回调
onActivity?.(payload)
onPhaseChange?.(payload)

// dispatch 分支
case 'activity': ...
case 'phase_change': ...
```

---

## 7. 数据流与状态模型

### 7.1 单条助手消息扩展字段

```typescript
interface AssistantMessage {
  role: 'assistant'
  text: string
  thinking?: string           // 仅 ADMIN 累积
  pipelineStep: number        // 1–6 宏观步
  statusText: string          // StatusLine 文案
  activities: ActivityItem[]  // 可选
  timeline: TimelineStep[]    // 微观节点列表
  progressCollapsed: boolean  // 执行详情折叠
  // ... 现有 result / chartSpec / intermediateSteps
}

interface TimelineStep {
  node: string
  label: string
  phase: string
  status: 'running' | 'done' | 'fail' | 'skipped'
  durationMs?: number
  summary?: string
  subtitle?: string
  active: boolean
  done: boolean
}
```

### 7.2 `onProgress` 更新逻辑（伪代码）

```javascript
onProgress: (evt) => {
  upsertTimelineStep(msg, evt)
  msg.pipelineStep = nodeToPipelineStep(evt.node)
  msg.statusText = evt.status === 'running' ? `正在${evt.label}…` : ''
  if (evt.phase) msg.currentPhase = evt.phase
}
```

### 7.3 性能

- `thinking_delta` / `text_delta` 高频：继续用字符串拼接，避免每 token 触发整表重渲染（可按 50ms `requestAnimationFrame` 批量刷 DOM，与 DAR 方案一致）。
- 完成后 `timeline` 保留用于折叠区展示，不写入会话 API 响应（或仅 ADMIN trace 可查）。

---

## 8. 分步实施指南

### Phase 0 · 安全热修（0.5d · P0）

| # | 任务 | 文件 |
|---|------|------|
| 0.1 | `thinking_delta_queue` 仅 ADMIN 创建 | `runner.py` |
| 0.2 | 各节点 `thinking_queue` 随 configurable 传递（已有则加角色判断） | `nodes.py` 等 |
| 0.3 | 前端 `canShowThinking` + 条件渲染 + 不注册 `onThinkingDelta` | `Ask.vue`, `ask.js` |
| 0.4 | 配置 `LLM_THINKING_STREAM_ADMIN_ONLY` | `settings.py`, `.env.example` |

**验收**：SCHOOL 用户问数，Network 面板无 `thinking_delta` 事件；界面无思考面板。

### Phase 1 · 布局重组 + 微观时间线（1–1.5d · P0）

| # | 任务 | 文件 |
|---|------|------|
| 1.1 | 新建 `AskTimeline.vue`、`AskPipelineHeader.vue` | `frontend/src/components/ask/` |
| 1.2 | `Ask.vue` 按 §4 线框重组 DOM | `Ask.vue` |
| 1.3 | `onProgress` 保存 `node`/`detail`，`formatStepSubtitle` | `Ask.vue` 或 `askProgress.js` |
| 1.4 | 完成后默认折叠执行详情 | `Ask.vue` |
| 1.5 | 接入 `PipelineStrip`（复用 insight 组件） | `AskPipelineHeader.vue` |

**验收**：流式问数时顶栏 6 步推进；时间线有图标与副文案；完成后折叠详情。

### Phase 2 · 后端 progress 增强（1d · P1）

| # | 任务 | 文件 |
|---|------|------|
| 2.1 | `node_to_phase()` + `summary` 脱敏生成 | `log_utils.py` 或新 `progress_payload.py` |
| 2.2 | 扩展 `progress_event()` 载荷 | `streaming.py`, `runner.py` |
| 2.3 | span 写入 `durationMs` 并在 progress 带出 | `nodes.py` `_span` / collector |
| 2.4 | 前端优先展示 `summary` / `durationMs` | `AskTimeline.vue` |

**验收**：`progress` SSE 含 `phase`、`summary`（无表名）、`durationMs`。

### Phase 3 · activity + 动效打磨（0.5–1d · P2）

| # | 任务 |
|---|------|
| 3.1 | 后端 `activity_event()`，阶段切换时推送 |
| 3.2 | `AskActivityFeed.vue` 或复用 `ActivityFeed` |
| 3.3 | CSS 微光扫过、步骤完成过渡动画 |
| 3.4 | `phase_change` 事件（可选） |

---

## 9. 配置项

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_THINKING_ENABLED` | `false` | DeepSeek 思考模式 |
| `LLM_THINKING_STREAM` | `true` | 是否 SSE 推送思考 |
| `LLM_THINKING_STREAM_ADMIN_ONLY` | `true` | **仅 ADMIN** 接收 `thinking_delta` |
| `ASK_PROGRESS_COLLAPSE_ON_DONE` | `true` | 完成后折叠执行详情 |
| `ASK_THINKING_DEFAULT_OPEN` | `false` | ADMIN 思考面板默认是否展开 |

---

## 10. 验收标准

### 10.1 功能

- [ ] 流式问数顶栏展示 6 步 Pipeline，随节点推进高亮正确阶段
- [ ] 执行详情时间线含：状态图标、中文标签、副文案、耗时（Phase 2+）
- [ ] 回答正文流式显示；完成后图表表格正常
- [ ] **SCHOOL / OPERATOR**：无思考面板、无 `thinking_delta` SSE
- [ ] **ADMIN**：可展开思考过程；SQL 仍仅 ADMIN（与现网一致）
- [ ] 完成后执行详情默认折叠，可手动展开

### 10.2 安全

- [ ] `summary` / 时间线副文案经人工 spot check：**不出现**业务物理表名、列名
- [ ] 非 ADMIN 抓包验证：无 `thinking_delta` 帧
- [ ] 会话历史 API 不返回 `thinking` 字段

### 10.3 体验

- [ ] 任意 3s 窗口内：有 `progress` / `text_delta` / `activity` 之一（无长时间空白）
- [ ] 移动端窄屏：Pipeline Strip 可换行，不撑破布局

---

## 11. 风险与降级

| 风险 | 降级 |
|------|------|
| `summary` 脱敏遗漏表名 | 回退为仅显示 `count` / `rowCount` 数值，不用 LLM 生成摘要 |
| `durationMs` 不准 | 前端隐藏耗时，仅显示 done/active |
| 组件过重影响 Ask 首屏 | Pipeline 组件懒加载；执行详情虚拟列表（>30 步时） |
| ADMIN 仍需要表名调试 | 继续用现有 SQL 块 + Trace 后台；思考过程不作为唯一调试入口 |

---

## 附录 A · 文件变更清单（预估）

```text
backend/
  app/agent/runner.py              # ADMIN thinking 门控 + progress 增强
  app/agent/streaming.py           # progress_event v2, activity_event
  app/agent/log_utils.py           # node_to_phase, summary  helpers
  config/settings.py               # LLM_THINKING_STREAM_ADMIN_ONLY

frontend/
  src/views/Ask.vue                # 布局重组
  src/api/ask.js                   # SSE 回调扩展
  src/utils/pipelineMapper.js      # phase 常量
  src/components/ask/
    AskPipelineHeader.vue
    AskTimeline.vue
    AskThinkingPanel.vue
  src/styles/ask-stream.css        # 可选：流式主题

docs/
  13-ASK_STREAM_UI_PLAN.md            # 本文档
```

---

## 附录 B · 与现有文档关系

| 文档 | 关系 |
|------|------|
| [15-DEEP_ANALYTICS_REPORT_PLAN.md](./15-DEEP_ANALYTICS_REPORT_PLAN.md) §6.9 | SSE `text_delta` / 活动 Feed 理念一致；DAR 用 `scope` 字段，Ask 用 `phase` |
| [12-CHART_VISUALIZATION_PLAN.md](./12-CHART_VISUALIZATION_PLAN.md) | `build_chart` 节点在时间线「回答」阶段展示 |
| [91-PROMPT_SECURITY.md](./91-PROMPT_SECURITY.md) | 思考过程视为高敏感 Prompt 泄漏面，纳入 ADMIN 门控 |
| [02-PROGRESS.md](./02-PROGRESS.md) | Phase 0 完成后更新问数 UI 完成度 |
