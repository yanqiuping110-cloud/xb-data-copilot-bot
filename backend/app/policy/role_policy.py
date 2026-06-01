"""
角色数据范围策略（与 sql_guard 配合）。

规则摘要：
- ADMIN / OPERATOR：业务 SQL 不强制 sch_id（仍受表白名单约束）。
- SCHOOL：必须 active_sch_id ∈ bound_sch_ids，SQL 网关注入 sch_id 条件。
"""

from app.core.context import UserContext, UserRole


class PolicyError(Exception):
    """策略拒绝：返回 403 与业务错误码。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def require_school_scope(ctx: UserContext) -> int:
    """
    学校账户问数前校验：必须已选 active_sch_id 且在绑定校列表内。

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


def applies_sch_id_filter(ctx: UserContext) -> bool:
    """是否需要在生成/执行 SQL 时注入 sch_id 过滤。"""
    return ctx.role == UserRole.SCHOOL
