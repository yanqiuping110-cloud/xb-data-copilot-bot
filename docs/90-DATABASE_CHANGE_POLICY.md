# 数据库变更策略

> 问数项目对 **业务库** 与 **问数库** 采用不同 SQL 权限策略，代码层 + 数据库账号双保险。

---

## 一、业务库 `MYSQL_BUSINESS_*`（如 `stugrow_sport`）

### 禁止（应用与问数链路）

| 类型 | 禁止内容 |
|------|----------|
| **DML** | `INSERT` / `UPDATE` / `DELETE` / `REPLACE` 等一切改数据操作 |
| **DDL** | `CREATE` / `ALTER` / `DROP` / `RENAME` / `TRUNCATE` 等一切改表结构操作 |
| **其他** | 多语句、`GRANT` / `REVOKE` 等 |

### 允许

- 仅 **`SELECT`**（经 `sql_guard` + `assert_business_readonly_sql` 校验）

### 代码入口

- `app/db/sql_policy.py` → `assert_business_readonly_sql()`
- `app/sql/guard.py` → `validate_sql()`
- `app/sql/executor.py` → `execute_readonly()`

### 运维建议

MySQL 账号 **`MYSQL_BUSINESS_USER` 仅授予 `SELECT`**，即使应用有漏洞也无法写库。

表结构由体育业务团队维护，**本仓库不通过 API 变更业务库结构**。

---

## 二、问数库 `MYSQL_COPILOT_*`（如 `study_demo`）

### 禁止（应用运行时）

| 类型 | 禁止内容 |
|------|----------|
| **DDL** | 增删改表、增删改字段、`TRUNCATE` 等一切改表结构操作 |
| **物理 DELETE** | `DELETE FROM ...` — 删除数据须逻辑删除 |

### 允许（应用运行时）

| 类型 | 说明 |
|------|------|
| **INSERT / UPDATE** | 用户、审计、问数记录等 |
| **逻辑删除** | `UPDATE ... SET deleted = 1`（`0` 未删除，`1` 已删除） |
| **SELECT** | 登录校验、列表查询等（默认 `WHERE deleted = 0`） |

### 逻辑删除字段

所有 `copilot_*` 表均含：

```sql
deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除'
```

已有库执行：`scripts/sql/copilot/V002__add_deleted_logical_delete.sql`

问数库 **表结构变更** 只能：

1. 新增 `backend/scripts/sql/copilot/V00x__描述.sql`
2. 由 DBA / 开发 **人工** 在目标库执行
3. 禁止在 `backend/app/` 内写 DDL，禁止 FastAPI 请求触发 DDL

### 代码 enforcement

- `app/db/copilot.py`：SQLAlchemy 钩子拦截 **DDL + 物理 DELETE**
- `app/db/sql_policy.py` → `assert_copilot_runtime_sql()`
- `app/auth/repositories.py`：查询默认 `deleted=0`；`replace_schools` 使用逻辑删除

### 人工执行 DDL

见 [backend/scripts/sql/README.md](../backend/scripts/sql/README.md)

```powershell
# 可选辅助脚本（须 --manual-confirm，不走应用引擎）
python scripts/apply_ddl_to_env_db.py --manual-confirm
```

---

## 三、版本 SQL 文件

```text
backend/scripts/sql/
├── README.md
└── copilot/
    ├── V001__init_copilot_tables.sql
    ├── V002__add_deleted_logical_delete.sql
    └── V003__...sql          # 后续变更递增
```

**规则：**

- 已执行过的版本文件 **不要修改**，只新增更高版本号  
- 文件头注释：环境、作者、日期、回滚说明  
- `scripts/ddl_copilot.sql` 保留为兼容入口，内容与 V001 同步，新变更以 `V00x` 为准  

---

## 四、与问数 `/ask` 的关系

LangGraph 生成或 MVP 硬编码的 SQL **只在业务库执行**，且必须：

1. 通过 `validate_sql()`（SELECT + 白名单 + LIMIT）  
2. 通过 `assert_business_readonly_sql()`（executor 二次校验）  

**永远不会**对业务库或问数库在问数链路中执行 DDL。

---

## 五、相关测试

```powershell
cd backend
pytest tests/test_sql_policy.py tests/test_sql_guard.py -q
```
