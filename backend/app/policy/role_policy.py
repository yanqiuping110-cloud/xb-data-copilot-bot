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
    lines = [
        "- 方言：MySQL 5.7，仅单条 SELECT，不要 INSERT/UPDATE/DELETE",
        "- 只能使用上表白名单中的表",
        (
            "- 涉及多表 JOIN 时：FROM/JOIN 中每张表必须定义短别名"
            "（如 sport_activity_qzs_record r、sport_project p）"
        ),
        (
            "- 多表查询时 SELECT、WHERE、GROUP BY、ORDER BY、HAVING 中的字段"
            "必须带表别名前缀（如 r.create_time、p.project_name），禁止裸写字段名"
        ),
        (
            "- 按项目名称过滤时使用 sport_project.project_name（别名 p.project_name）；"
            "运动值字段为 sport_activity_qzs_record.sport_value（别名 r.sport_value）"
        ),
    ]
    lines.extend(build_llm_sch_id_constraints(ctx, settings=settings))
    lines.append(
        "- 【问句匹配的过滤条件】与【表默认过滤条件】中的条目必须写入 WHERE，不可省略"
    )
    lines.append(
        "- 字段取值映射：问句提及项目名/枚举别名时，用对应 column = 库内值 过滤"
        "（如 project_id=1 或 JOIN sport_project 后 p.project_name='跳绳'）"
    )
    lines.append(
        "- 只能使用【候选表字段清单】中的真实 column_name，"
        "禁止编造 student_name、enrollment_year 等未列出的字段"
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
