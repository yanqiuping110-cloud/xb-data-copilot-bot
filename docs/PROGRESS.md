# 问数项目 · 开发进度

> 与 [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) 四周计划对照更新。  
> **代码注释规范**：所有业务代码须写**中文注释**（见开发计划 §0、§5.1）。

---

## 总览（截至 2026-06-01）

| 模块 | 进度 | 说明 |
|------|------|------|
| 仓库结构 | ✅ 完成 | `backend/` + `frontend/` monorepo |
| 后端配置 | ✅ 完成 | `APP_ENV`、双 MySQL、JWT、LLM 等 |
| 用户与认证 | ✅ 完成 | 登录、切换学校、JWT、`/me` |
| 超管用户管理 | ✅ 完成 | CRUD、学校绑定 |
| 角色数据策略 | ✅ 完成 | `role_policy` + 单测 |
| 健康检查 | ✅ 完成 | `/health`、`/ready`（含 MySQL 探测） |
| 前端骨架 | 🟡 进行中 | 登录页、首页占位；问数对话页未做 |
| 问数 `/ask` | ⬜ 未开始 | LangGraph、sql_guard、业务 SQL |
| 可观测写入 | ⬜ 未开始 | `copilot_ask_turn` / `copilot_ask_span` / `copilot_audit_log` |
| 指标与 L1 降级 | ⬜ 未开始 | `copilot_metric_definition`、`copilot_sql_example` |
| 评测集 | ⬜ 未开始 | `docs/EVAL_QUESTIONS.md` |

---

## 第 1 周（地基 + 可观测）

| 任务 | 状态 | 备注 |
|------|------|------|
| FastAPI 工程与 Docker 骨架 | ✅ | `backend/deploy`、`Dockerfile` |
| `ddl_copilot.sql` + `seed_admin` | ✅ | 需本机执行 MySQL |
| JWT 登录 + `role_policy` 单测 | ✅ | 7 个 pytest 通过 |
| `/admin/users` | ✅ | 仅 ADMIN |
| MySQL 业务只读 + `/ask` 假数据 | ⬜ | 下一步 |
| `tracer` 写 ask/audit 表 | ⬜ | |
| 中文注释规范落地 | ✅ | 后端/前端核心文件已补注释 |

---

## 第 2～4 周

| 周 | 重点 | 状态 |
|----|------|------|
| 第 2 周 | LangGraph 7 节点、sql_guard、表白名单 | ⬜ |
| 第 3 周 | 前端问数页、反馈、指标配置 | ⬜ |
| 第 4 周 | 评测回归、部署文档、公司环境 | ⬜ |

---

## 近期变更记录

| 日期 | 内容 |
|------|------|
| 2026-06-01 | 拆分为 `backend/`、`frontend/`；认证与用户管理 API |
| 2026-06-01 | 统一 `backend/.venv`；补充中文注释与 `PROGRESS.md` |
| 2026-06-01 | DDL 表名改为 `copilot_*` 前缀，字段补全 COMMENT；ORM/seed/文档同步 |

---

## 下一步建议

1. 本机：`ddl_copilot.sql` + `seed_admin.py`，Postman 走通登录与创建运营/学校账号。  
2. 实现 `POST /api/v1/ask` MVP（硬编码 SQL + `sch_id` 注入）。  
3. 前端：问数对话页、学校切换、超管用户管理页。
