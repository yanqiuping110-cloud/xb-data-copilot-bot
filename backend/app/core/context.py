"""
请求上下文：JWT 校验后注入的当前用户身份。

问数、审计、SQL 策略均只信任此对象，不信任前端 body 中的 schId/role。
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """问数系统三类角色（与后台 PeopleRoleType 命名独立）。"""

    ADMIN = "ADMIN"  # 超管：用户管理 + 全平台数据
    OPERATOR = "OPERATOR"  # 运营：可问数；无用户管理、无元数据治理
    SCHOOL = "SCHOOL"  # 学校：仅绑定校数据，须 active_sch_id


class UserContext(BaseModel):
    """
    单次 HTTP 请求内的用户上下文。

    trace_id：全链路追踪 ID，写入 copilot_ask_turn / copilot_audit_log。
    active_sch_id：学校账户当前选中校；运营/超管为 None。
    """

    trace_id: str = Field(description="本请求追踪 ID（UUID）")
    user_id: int = Field(description="copilot_sys_user.id")
    username: str
    role: UserRole
    active_sch_id: Optional[int] = Field(
        default=None,
        description="学校账户当前校 ID；问数前须已选择",
    )
    bound_sch_ids: list[int] = Field(
        default_factory=list,
        description="学校账户绑定的全部 sch_id",
    )
    active_scopes: dict[str, Any] = Field(
        default_factory=dict,
        description="JWT 当前数据范围上下文，键为 dimension_code",
    )
    effective_policy: Any = Field(
        default=None,
        description="问数入口加载的 EffectivePolicy（运行时注入，非 JWT 字段）",
    )
    client_ip: Optional[str] = Field(default=None, description="客户端 IP，审计用")
    token_scope: Optional[str] = Field(
        default=None,
        description="JWT scope；embed 模式禁止访问管理接口",
    )
