# 问数项目 · 开发进度

> 与 [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) **6 周计划**对照更新（v2.0：元数据知识库 + 语义库 + 混合召回 + 多阶段推理）。  
> **代码注释规范**：所有业务代码须写**中文注释**（见开发计划 §0、§5.1）。

---

## 总览（截至 2026-06-05）

| 模块 | 进度 | 说明 |
|------|------|------|
| 仓库结构 | ✅ 完成 | `backend/` + `frontend/` monorepo |
| 后端配置 | ✅ 完成 | `APP_ENV`、双 MySQL、JWT、LLM、Embedding 配置项 |
| 用户与认证 | ✅ 完成 | 登录、切换学校、JWT、`/me` |
| 超管用户管理 | ✅ 完成 | CRUD、学校绑定 |
| 角色数据策略 | ✅ 完成 | `role_policy` + 单测 |
| 健康检查 | ✅ 完成 | `/health`、`/ready`（含 MySQL 探测） |
| 问数 `/ask` | ✅ 完成 | LangGraph 基线 + L1 + LLM |
| 可观测写入 | ✅ 完成 | `tracer` 写 turn/span/audit |
| 前端问数页 | ✅ 完成 | 对话页 + 学校切换 + 超管用户管理页 |
| 动态语义 L1 | ✅ 完成 | `copilot_sql_example` + `copilot_metric_definition` |
| LangGraph 7 节点基线 | ✅ 完成 | `app/agent/`；待拆分为多阶段召回链 |
| `retrieve_context` | ✅ 已演进 | 拆为 `extract_keywords` → 三路 `recall_*` → `build_llm_context` |
| LLM `generate_sql` | ✅ 完成 | OpenAI 兼容 API，L2 精简重试 1 次 |
| **V004 元数据 DDL** | ✅ 完成 | `scripts/sql/copilot/V004__meta_knowledge.sql` |
| **元数据后端** | ✅ 完成 | `app/meta/` introspect + CRUD + refresh |
| **`/admin/meta` API** | ✅ 完成 | introspect / tables / columns / refresh |
| **白名单** | ✅ 更新 | 优先 `copilot_table_meta.status=1` |
| **混合召回（ES）** | ✅ 完成 | `HybridRetriever` + keyword 降级；接入 LangGraph |
| **多阶段 LangGraph** | ✅ 完成 | 召回链 + `correct_sql`；见 §6.1 |
| **前端 meta 管理页** | ✅ 完成 | 表/字段/关系/取值/指标/L1/badcase + 问数页反馈 |
| **Agent Memory（第 6 周）** | ✅ 完成 | Memory + 偏好抽屉 + badcase→L1 草稿 + 多轮评测子集 |
| 评测集 | 🟡 部分 | `EVAL_QUESTIONS.md` + `replay_eval.py`（Memory 子集）；全量第 8 周 |

---

## 第 1～2 周（已完成）

| 任务 | 状态 | 备注 |
|------|------|------|
| FastAPI 工程与 Docker 骨架 | ✅ | `backend/deploy`、`Dockerfile` |
| `ddl_copilot.sql` + `seed_admin` | ✅ | 需本机执行 MySQL |
| JWT 登录 + `role_policy` 单测 | ✅ | pytest 通过 |
| `/admin/users` | ✅ | 仅 ADMIN |
| LangGraph + `/ask` + sql_guard | ✅ | L1 + LLM 路径 |
| `tracer` 写 ask/audit 表 | ✅ | `app/observability/tracer.py` |
| 前端问数 + 用户管理 | ✅ | `Ask.vue`、`AdminUsers.vue` |
| L1 种子 | ✅ | `seed_sql_examples.py` |

---

## 第 3 周（元数据知识库 · 后端代码完成，待本机联调）

| 任务 | 状态 | 备注 |
|------|------|------|
| `V004__meta_knowledge.sql` | ✅ | 表/字段/关系/取值/指标关联 |
| `BusinessSchemaIntrospector` | ✅ | `information_schema` 只读 |
| `GET /admin/meta/introspect/tables/{name}` | ✅ | 预览不落库 |
| `POST/PUT /admin/meta/tables` | ✅ | 注册 + 人工定义 |
| `POST .../refresh-from-business` | ✅ | auto 刷新，保护 manual |
| `MetaRepository` + `MetaService` | ✅ | `app/meta/` |
| `require_meta_manager` | ✅ | ADMIN / OPERATOR |
| `test_meta_effective.py` | ✅ | effective + 表名校验 |
| `test_meta_index_text.py` | ✅ | 索引 search_text 拼装单测（无需 ES） |
| 本机执行 V004 迁移 | ⬜ | 需手工跑 SQL |
| `seed_semantic_meta.py` | ✅ | 首表 `sport_activity_qzs_record` + project_id 取值 |
| `MetaKnowledgeService` | ✅ | `app/meta/index_service.py` + `app/retrieval/` |
| ES `build_search_index` | ✅ | CLI + `POST /admin/meta/rebuild-index`（需 ES + Embedding） |
| 本机 ES/Embedding 联调 | ✅ | rebuild-index / build_search_index 已验证 |

---

## 第 4 周（已完成）

| 任务 | 状态 | 备注 |
|------|------|------|
| `AdminMetaTables.vue` | ✅ | 表列表、编辑、刷新结构、重建索引 |
| `AdminMetaTableNew.vue` | ✅ | 表名 → introspect → 双列备注 → 保存 |
| `AdminMetaColumns.vue` | ✅ | 字段双列、有效定义预览、逐字段保存 |
| 关系 / 取值 / 指标 / L1 样例页 | ✅ | `/admin/meta/relations` 等 |
| `POST /api/v1/feedback` + badcase 列表 | ✅ | 问数页 👍/👎/badcase；运营修正 SQL → 补 L1 |
| 路由守卫 ADMIN/OPERATOR | ✅ | `/admin/meta/*` |

---

## 第 5 周（已完成）

| 任务 | 状态 | 备注 |
|------|------|------|
| `HybridRetriever` | ✅ | `app/retrieval/hybrid.py`；ES 向量/全文 + MySQL keyword 降级 |
| `extract_keywords` | ✅ | `app/retrieval/keyword_extractor.py` |
| 三路 `recall_*` 节点 | ✅ | `app/agent/recall_nodes.py`；span 可观测 |
| `merge` / `filter` / `build_llm_context` | ✅ | `app/agent/context_builder.py` |
| `correct_sql` | ✅ | 校验失败重试 1 次；`route_after_validate` 路由 |
| ES 降级追踪 | ✅ | `recall_mode=keyword_fallback` 写入 span |
| `/ready` ES 探针 | ✅ | `checks.elasticsearch` |
| `test_hybrid_retriever.py` | ✅ | 关键词/排序/路由单测（无需 ES） |

---

## 第 6 周（Agent Memory · 已完成）

| 任务 | 状态 | 备注 |
|------|------|------|
| `V007__agent_memory.sql` | ✅ | session 扩展 + `copilot_user_preference` + `copilot_session_summary` |
| `app/memory/` | ✅ | `SessionService`、`MemoryService`、`reference_resolver`、`badcase_l1` |
| `GET/POST/DELETE /api/v1/sessions` | ✅ | 含 messages、20 条上限淘汰 |
| `GET/PUT/DELETE /api/v1/memory/preferences` | ✅ | key 白名单 |
| LangGraph `load_session_memory` 等 3 节点 | ✅ | Fail-open；注入 `build_llm_context` |
| 问数页左侧对话栏 + 偏好抽屉 | ✅ | 新对话 / 切换 / 删除 / 偏好设置 |
| 本机执行 V007 迁移 | ✅ | 用户已执行 |
| badcase → L1 一键草稿（P3） | ✅ | `POST .../draft-sql-example`；`draft` 样例不参与匹配 |
| `EVAL_QUESTIONS.md` + `replay_eval.py` | ✅ | 8 条多轮用例 `docs/eval/memory_multiturn.json` |

---

## LangGraph 流水线

### 已落地（基线）

| 节点 | 实现位置 |
|------|----------|
| `normalize_question` | `app/agent/nodes.py` |
| `retrieve_context` | `app/agent/context_retriever.py` |
| `match_curated` | `app/ask/query_match.py`（L1 + MVP） |
| `generate_sql` | `app/agent/llm_sql.py` |
| `validate_sql` | `app/sql/guard.py` |
| `apply_policy` | `app/agent/nodes.py` |
| `execute_sql` | `app/sql/executor.py` |
| `format_answer` | `app/agent/nodes.py` |

### 已新增（第 5 周）

| 节点 | 实现位置 |
|------|----------|
| `extract_keywords` | `app/agent/recall_nodes.py` |
| `recall_columns` / `recall_metrics` / `recall_field_values` | `app/agent/recall_nodes.py` + `app/retrieval/hybrid.py` |
| `merge_retrieved_info` / `filter_tables` / `filter_metrics` / `build_llm_context` | `app/agent/recall_nodes.py` + `app/agent/context_builder.py` |
| `correct_sql` | `app/agent/nodes.py` |

入口：`POST /api/v1/ask` → `app/ask/service.py` → `app/agent/runner.py`。

---

## 元数据 API（已实现）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/meta/introspect/tables/{tableName}` | 只读预览业务库结构 |
| GET/POST/PUT | `/api/v1/admin/meta/tables` | 表元数据 CRUD |
| POST | `/api/v1/admin/meta/tables/{id}/refresh-from-business` | 刷新 auto，保护 manual |
| GET/PUT | `/api/v1/admin/meta/tables/{id}/columns`、`/columns/{id}` | 字段列表与人工更新 |
| POST | `/api/v1/admin/meta/rebuild-index` | 全量重建 ES 字段/指标/取值索引 |

### 新增脚本与模块（2026-06-05）

| 路径 | 说明 |
|------|------|
| `scripts/seed_semantic_meta.py` | 注册首表、人工字段定义、`copilot_field_value`（跳绳/跑步） |
| `scripts/build_search_index.py` | MySQL 元数据 → ES 三索引（column/metric/value） |
| `app/meta/index_text.py` | effective 描述 + 别名 → 索引文本 |
| `app/meta/index_service.py` | `MetaKnowledgeService.rebuild_all()` |
| `app/retrieval/embedding.py` | Ollama 兼容 Embedding 客户端 |
| `app/retrieval/es_client.py` | ES 索引创建与 bulk 写入 |

---

## 近期变更记录

| 日期 | 内容 |
|------|------|
| 2026-06-01 | 拆分为 `backend/`、`frontend/`；认证与用户管理 API |
| 2026-06-02 | `POST /api/v1/ask` MVP、sql_guard、tracer、前端问数页 |
| 2026-06-03 | LangGraph + LLM；开发计划 v2.0/v2.1 |
| 2026-06-03 | **第 3 周启动**：V004 DDL、`app/meta`、`/admin/meta` API、白名单接 table_meta |
| 2026-06-05 | 语义库 CRUD API（关系/取值/指标/L1）+ feedback/badcase + 前端全套管理页 |
| 2026-06-05 | **第 5 周**：`HybridRetriever`、多阶段 LangGraph 召回链、`correct_sql`、单测 53 通过 |

---

## 本机验证

**仅需 MySQL**（无 ES/Redis 也可跑 API、种子与单测）：

```powershell
# 1. 执行迁移（copilot 库）
mysql -u copilot -p copilot < backend/scripts/sql/copilot/V004__meta_knowledge.sql

# 2. 元数据种子（需业务库可连、表 sport_activity_qzs_record 存在）
cd backend
$env:APP_ENV = "development"
python scripts/seed_semantic_meta.py

# 3. 启动 API
uvicorn app.main:app --reload --port 8000

# 4. introspect 预览（需 ADMIN/OPERATOR JWT）
# GET /api/v1/admin/meta/introspect/tables/sport_activity_qzs_record
```

```powershell
cd backend
pytest tests/test_meta_effective.py tests/test_meta_index_text.py -q
```

**有 Docker ES + Ollama Embedding 时**再执行索引构建：

```powershell
python scripts/build_search_index.py
# 或 POST /api/v1/admin/meta/rebuild-index
```

---

## 下一步

1. **多轮评测**：`python scripts/replay_eval.py --subset memory --token "<JWT>"`  
2. **第 7 周**：动态数据权限（`V008` + `EffectivePolicy`）。  
3. **第 8 周**：扩展 `EVAL_QUESTIONS` 至 15～30 条开放域 + 全量 `replay_eval`。  
4. 运营闭环：badcase → 转 L1 草稿 → 审核发布 → 再问数验证。
