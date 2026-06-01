"""角色数据范围策略单元测试。"""

import pytest

from app.core.context import UserContext, UserRole
from app.policy.role_policy import PolicyError, applies_sch_id_filter, require_school_scope


def test_school_requires_active_sch_id():
    """未选学校时问数应被拒绝。"""
    ctx = UserContext(
        trace_id="t1",
        user_id=1,
        username="sch",
        role=UserRole.SCHOOL,
        bound_sch_ids=[1140, 1220],
    )
    with pytest.raises(PolicyError) as exc:
        require_school_scope(ctx)
    assert exc.value.code == "NO_ACTIVE_SCHOOL"


def test_school_forbidden_sch():
    """active_sch_id 不在绑定列表内应拒绝。"""
    ctx = UserContext(
        trace_id="t2",
        user_id=1,
        username="sch",
        role=UserRole.SCHOOL,
        active_sch_id=9999,
        bound_sch_ids=[1140],
    )
    with pytest.raises(PolicyError) as exc:
        require_school_scope(ctx)
    assert exc.value.code == "SCHOOL_FORBIDDEN"


def test_admin_no_sch_filter():
    """超管不注入 sch_id 过滤。"""
    ctx = UserContext(
        trace_id="t3",
        user_id=1,
        username="admin",
        role=UserRole.ADMIN,
    )
    assert applies_sch_id_filter(ctx) is False


def test_operator_no_sch_filter():
    """运营不注入 sch_id 过滤。"""
    ctx = UserContext(
        trace_id="t4",
        user_id=2,
        username="ops",
        role=UserRole.OPERATOR,
    )
    assert applies_sch_id_filter(ctx) is False
