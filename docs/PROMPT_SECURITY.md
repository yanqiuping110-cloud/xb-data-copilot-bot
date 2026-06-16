# Prompt Injection 与数据权限运营规范

> 第 13～14 周 · 与 [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) §11.9 对齐。

## 威胁模型

| 类型 | 攻击面 | 服务端兜底 |
|------|--------|------------|
| 直接劫持 | 用户问句 | `sql_guard` 仅 SELECT；System 拒令 |
| Memory 污染 | 会话槽位 / 偏好 | 结构化槽位 + 白名单 key + 定界符 |
| 间接注入 | meta 备注 / 代码 snippet | `sanitize_recall_text` |
| 权限绕过 | 复制历史 SQL | 每次独立 Scope + guard |

**原则**：不信任 LLM 输出；Prompt 层纵深 + 执行层 Fail-closed。

## 定界符约定

不可信内容经 `wrap_untrusted` 包裹：

```text
<<<UNTRUSTED:user_question>>>
…用户问句…
<<<END>>>
```

可信块（服务端生成，排在前面）：

- `【数据范围】` / `【可见表】` / `【禁止字段】`（DataScope）
- `【当前用户角色】`

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `PROMPT_BOUNDARY_ENABLED` | true | 问句 / Memory 定界 |
| `PROMPT_SANITIZE_RECALL_ENABLED` | true | 召回片段清洗 |
| `PROMPT_INJECTION_LOG_ENABLED` | true | 清洗命中写 span |
| `POLICY_DATA_SCOPE_ENABLED` | false | 启用配置驱动 DataScope |
| `POLICY_DEFAULT_DENY` | true | 无 grant 拒绝问数 |

## 运营规范

1. **勿在** `description_manual`、L1 样例、代码 artifact 摘要中写入「忽略系统指令」类文本。
2. 敏感列通过 `copilot_column_deny` 配置，不依赖 Prompt 约束。
3. badcase 若因注入导致误答：补 meta 清洗 + 增加 `inj-*` 回归用例。

## 评测

```powershell
cd backend
python scripts/replay_eval.py --subset injection --token "<JWT>"
```

机器可读：`docs/eval/prompt_injection.json`。  
验收：`injection_blocked_rate=100%`，`leaked_sql_count=0`。
