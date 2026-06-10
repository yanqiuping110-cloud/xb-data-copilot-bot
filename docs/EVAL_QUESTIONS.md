# 问数评测问句集

> 与 [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) 对齐。第 6 周先交付 **多轮 Memory 子集**；第 8 周扩展至 15～30 条开放域 + `replay_eval.py` 全量回归。

## 使用方式

```powershell
cd backend
$env:APP_ENV = "development"
# 需有效 JWT（学校/运营/超管）与 copilot + 业务库可连
python scripts/replay_eval.py --subset memory --token "<JWT>"
```

机器可读用例：`docs/eval/memory_multiturn.json`。

---

## 一、开放域单轮（第 8 周扩展）

| # | 角色 | 问句 | 期望路径 |
|---|------|------|----------|
| O-01 | SCHOOL | 本校本月跳绳活动参与人数是多少？ | L1 或 LLM + 字段取值 `project_id=1` |
| O-02 | SCHOOL | 本校最近 7 天每日参与人数趋势？ | LLM + 指标 `qzs_weekly_trend` |
| O-03 | ADMIN | 昨日全平台活动参与人次汇总？ | L1 或 LLM；`adminOnly` |
| O-04 | SCHOOL | 本校跑步项目上周打卡人次？ | 字段取值召回 `project_id=20` |
| O-05 | SCHOOL | 对比本月跳绳与跑步参与人数？ | 多表 JOIN + 过滤 |

---

## 二、多轮 Memory 子集（第 6 周 · 5～8 条）

同 `sessionId` 下连续提问，验证 **L1 结构化槽位** 与 **指代消解**（span 含 `load_session_memory` / `resolve_references`）。

| ID | 角色 | 轮次 | 问句 | 验收要点 |
|----|------|------|------|----------|
| mem-01 | SCHOOL | 1 | 本校本月跳绳参与人数是多少？ | `status=success`；写 turn |
| mem-01 | SCHOOL | 2 | 按刚才的维度查上周 | `resolve_references` 命中；SQL 仍含跳绳/参与口径 |
| mem-02 | SCHOOL | 1 | 最近7天每日参与人数趋势 | 成功；`tables_used` 含活动表 |
| mem-02 | SCHOOL | 2 | 同上，但只要跳绳 | `matchAny` 指代；`project_id` 或项目过滤 |
| mem-03 | SCHOOL | 1 | 本校活动参与人数 | 成功 |
| mem-03 | SCHOOL | 2 | 再查一次 | `repeat_last` 指代；SQL 结构相近 |
| mem-04 | OPERATOR | 1 | 昨日全平台活动参与人次 | 超管/运营路径成功 |
| mem-04 | OPERATOR | 2 | 同样维度看本月 | 跨轮表名/时间范围合理 |
| mem-05 | SCHOOL | 1 | 本校本月跳绳参与人数 | 成功 |
| mem-05 | SCHOOL | 2 | （新对话）本校本月跳绳参与人数 | **新 sessionId** 无上一轮槽位；仍成功 |
| mem-06 | SCHOOL | 1 | 本校本月跳绳参与人数 | 用户偏好 `default_time_range=month` 已设置 |
| mem-06 | SCHOOL | 2 | 参与人数呢 | 偏好 + 槽位同时注入 Prompt |
| mem-07 | SCHOOL | 1 | 随便一个不存在的表 xyz 查询 | `fail` 或降级 |
| mem-07 | SCHOOL | 2 | 刚才那个再查 | 无槽位或 fail-open，**不 500** |
| mem-08 | SCHOOL | 1 | 本校本月跳绳参与人数 | L1 命中时 **不** 因 Memory 改变 SQL |
| mem-08 | SCHOOL | 2 | 本校本月跳绳参与人数 | 同 L1；`generate_sql` 未调用 |

### 鲁棒性 spot check（第 6 周）

| 场景 | 期望 |
|------|------|
| `SESSION_MEMORY_ENABLED=false` | 问数成功；span `memory_skipped=true` |
| 越权 `sessionId` | 零注入；服务端换新 session |
| Memory 读库失败 | Fail-open，问数仍成功 |
| Prompt Memory 超长 | 截断至 `MEMORY_PROMPT_MAX_CHARS` |

---

## 三、badcase → L1 闭环（P3）

1. 问数点踩 / 标记 badcase  
2. 运营在 Badcase 页 **修正 SQL** → **转 L1 草稿**  
3. 样例页审核：`meta_json.draft` 去掉、`degrade_priority` 调低  
4. 同问句再问 → L1 命中

---

## 四、指标（参考）

| 阶段 | 指标 |
|------|------|
| 第 6 周 Memory 子集 | 多轮用例 **≥ 80%** turn 成功；指代用例 **≥ 60%** span 可见 memory |
| 第 8 周开放域 | `degrade_level=0` 路径完成率 **≥ 60%** |
