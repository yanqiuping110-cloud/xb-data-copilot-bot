# 问数库 / 业务库 · SQL 版本变更（仅人工执行）

> 策略详见 [docs/DATABASE_CHANGE_POLICY.md](../../docs/DATABASE_CHANGE_POLICY.md)

## 目录

| 目录 | 库 | 说明 |
|------|-----|------|
| `copilot/` | `MYSQL_COPILOT_DATABASE` | 问数库表结构；**应用运行时禁止 DDL** |
| `business/` | `MYSQL_BUSINESS_DATABASE` | 业务库结构（一般不改，由业务团队维护） |

## 命名规范

```text
V{序号}__{简短英文描述}.sql
```

示例：`V001__init_copilot_tables.sql`、`V002__add_feedback_column.sql`

## 执行方式（人工）

1. 在目标环境确认当前已执行到的最大版本号  
2. 用 Navicat / mysql 客户端连接对应库  
3. 将 SQL 中 `USE copilot;` 改为实际库名（如 `USE study_demo;`）  
4. **逐文件、按版本号顺序**执行，勿在应用内自动跑 DDL  

可选辅助（需显式确认，仍视为人工操作）：

```powershell
cd backend
$env:APP_ENV = "development"
python scripts/apply_ddl_to_env_db.py --manual-confirm
```

## 禁止

- 在 `backend/app/` 内编写 `CREATE TABLE` / `ALTER TABLE` / `DROP TABLE`  
- 通过问数 API 或 LangGraph 对任一库执行 DDL/DML（业务库仅 SELECT）
