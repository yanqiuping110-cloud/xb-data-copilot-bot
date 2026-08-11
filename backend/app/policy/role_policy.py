"""
角色数据范围策略（与 sql_guard 配合）。

规则摘要：
- ADMIN / OPERATOR：业务 SQL 不强制 sch_id（仍受表白名单约束）。
- SCHOOL：必须 active_sch_id ∈ bound_sch_ids，SQL 网关注入 sch_id 条件。

演进（§11.7.1 / §11.6）：
- 第 7～12 周：`POLICY_SCH_ID_ENABLED=false` 时问数链路暂停 sch 逻辑，JWT/学校绑定 UI 保留。
- 第 13 周：`EffectivePolicy` 替代本模块中的硬编码 sch_id 分支。
"""

from __future__ import annotations

import re

from app.core.context import UserContext, UserRole
from config.settings import Settings, get_settings


class PolicyError(Exception):
    """策略拒绝：返回 403 与业务错误码。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def require_school_scope(ctx: UserContext) -> int:
    """
    学校账户问数前校验：必须已选 active_sch_id 且在绑定校列表内。

    第 13 周前由 `POLICY_SCH_ID_ENABLED` 控制是否在 runner 中调用；本函数本身不变。

    Returns:
        通过校验的 active_sch_id，供 SQL 注入使用。
    """
    if ctx.role != UserRole.SCHOOL:
        raise PolicyError("NOT_SCHOOL_ROLE", "仅学校账户需要校维度")
    if ctx.active_sch_id is None:
        raise PolicyError("NO_ACTIVE_SCHOOL", "请先选择学校")
    if ctx.bound_sch_ids and ctx.active_sch_id not in ctx.bound_sch_ids:
        raise PolicyError("SCHOOL_FORBIDDEN", "无权访问该学校数据")
    return ctx.active_sch_id


def applies_sch_id_filter(ctx: UserContext, *, settings: Settings | None = None) -> bool:
    """
    是否需要在生成/执行 SQL 时注入 sch_id 过滤。

    `POLICY_SCH_ID_ENABLED=false` 时恒为 False（第 7～12 周问数准确性攻坚）。
    """
    s = settings or get_settings()
    if not s.policy_sch_id_enabled:
        return False
    return ctx.role == UserRole.SCHOOL


def build_role_context_header(ctx: UserContext, *, settings: Settings | None = None) -> str:
    """Prompt 首行：明确当前角色与 sch_id 策略。"""
    role_label = {
        UserRole.ADMIN: "超管",
        UserRole.OPERATOR: "运营",
        UserRole.SCHOOL: "学校",
    }.get(ctx.role, ctx.role.value)
    if applies_sch_id_filter(ctx, settings=settings):
        return (
            f"【当前用户角色】{role_label}（{ctx.role.value}）"
            " — 必须在 WHERE 中使用 sch_id = :sch_id"
        )
    return (
        f"【当前用户角色】{role_label}（{ctx.role.value}）"
        " — 默认禁止添加 sch_id 条件，可查全平台"
    )


def build_llm_sch_id_constraints(ctx: UserContext, *, settings: Settings | None = None) -> list[str]:
    """按角色生成 LLM Prompt 中的 sch_id 约束说明。"""
    if applies_sch_id_filter(ctx, settings=settings):
        return [
            "- 当前用户为学校账户：必须在 WHERE 中使用 sch_id = :sch_id（不要写具体数字）",
        ]
    return [
        "- 当前用户为超管/运营：默认不要添加 sch_id 条件，可查全平台数据",
        "- 仅当用户明确指定某所学校时，才在 WHERE 中加 sch_id 条件（可用具体数字）",
    ]


def build_llm_sql_generation_constraints(
    ctx: UserContext,
    *,
    settings: Settings | None = None,
) -> list[str]:
    """LLM Prompt【生成约束】：方言、表白名单、JOIN 别名、sch_id 等。"""
    from app.system.sql_context import resolve_sql_context

    sql_ctx = resolve_sql_context(settings)
    lines = [
        f"- 方言：{sql_ctx.prompt_dialect_label}，仅单条 SELECT，不要 INSERT/UPDATE/DELETE",
        f"- {sql_ctx.aggregate_strategy_hint()}",
        "- 表名与列名仅可使用【允许查询的业务表】与【候选表字段清单】中已列出的名称，禁止引用未出现的表或字段",
        (
            "- 涉及多表 JOIN 时：FROM/JOIN 中每张表必须定义短别名"
            "（别名自定，如 t1、t2），且只能 JOIN 白名单内的表"
        ),
        (
            "- 多表查询时 SELECT、WHERE、GROUP BY、ORDER BY、HAVING 中的字段"
            "必须带表别名前缀，禁止裸写字段名"
        ),
        (
            "- 按项目/枚举过滤时：使用候选字段清单中的真实列名"
            "（如 project_id、project_name 等，以清单为准）"
        ),
    ]
    lines.extend(build_llm_sch_id_constraints(ctx, settings=settings))
    lines.append(
        "- 【问句匹配的过滤条件】与【表默认过滤条件】中的条目必须写入 WHERE，不可省略"
    )
    lines.append(
        "- 字段取值映射：问句提及项目名/枚举别名时，用对应 column = 库内值 过滤"
        "（具体 column 以【候选表字段清单】为准）"
    )
    lines.append(
        "- 只能使用【候选表字段清单】中的真实 column_name，"
        "禁止编造未列出的字段"
    )
    lines.append(
        "- SELECT 输出列 AS 别名必须用英文标识符（snake_case / metric_code），"
        "禁止中文别名；中文表头由系统在展示/导出时转换"
    )
    lines.append("- 输出仅包含 SQL，不要解释")
    return lines


LLM_JOIN_ALIAS_SYSTEM_HINT = (
    "多表 JOIN 时每张表必须取短别名，"
    "且 SELECT/WHERE/GROUP BY/ORDER BY/HAVING 中所有字段必须带表别名前缀，禁止裸写字段名。"
)


def strip_sch_id_for_broad_roles(
    sql: str,
    ctx: UserContext,
    *,
    settings: Settings | None = None,
) -> str:
    """
    超管/运营不要求 sch_id；若 LLM 误加 :sch_id 占位符则移除对应条件。

    `POLICY_SCH_ID_ENABLED=false` 时学校账户也走宽角色路径（移除 sch 条件）。
    避免 SQL 含 :sch_id 但未绑定参数导致执行失败。
    """
    if applies_sch_id_filter(ctx, settings=settings):
        return sql
    if ":sch_id" not in sql.lower():
        return sql

    cleaned = sql
    cleaned = re.sub(r"\s+AND\s+sch_id\s*=\s*:sch_id\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\bWHERE\s+sch_id\s*=\s*:sch_id\s+AND\s+",
        "WHERE ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bWHERE\s+sch_id\s*=\s*:sch_id\b", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()
