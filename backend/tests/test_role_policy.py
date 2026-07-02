"""角色数据范围策略单元测试。"""

import pytest

from app.core.context import UserContext, UserRole
from app.policy.role_policy import (
    PolicyError,
    applies_sch_id_filter,
    build_llm_sch_id_constraints,
    build_llm_sql_generation_constraints,
    require_school_scope,
    strip_sch_id_for_broad_roles,
)
from config.settings import Settings


def _settings_sch_on() -> Settings:
    return Settings(JWT_SECRET="test-secret", POLICY_SCH_ID_ENABLED=True)


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


def test_admin_llm_constraints_no_sch_id():
    ctx = UserContext(trace_id="t5", user_id=1, username="admin", role=UserRole.ADMIN)
    lines = build_llm_sch_id_constraints(ctx)
    assert any("不要添加 sch_id" in line for line in lines)


def test_school_llm_constraints_requires_sch_id():
    ctx = UserContext(trace_id="t6", user_id=1, username="sch", role=UserRole.SCHOOL)
    lines = build_llm_sch_id_constraints(ctx, settings=_settings_sch_on())
    assert any("sch_id = :sch_id" in line for line in lines)


def test_strip_sch_id_for_admin():
    ctx = UserContext(trace_id="t7", user_id=1, username="admin", role=UserRole.ADMIN)
    sql = (
        "SELECT SUM(sport_value) AS total FROM sport_activity_qzs_record "
        "WHERE sch_id = :sch_id LIMIT 5000"
    )
    cleaned = strip_sch_id_for_broad_roles(sql, ctx)
    assert ":sch_id" not in cleaned.lower()
    assert "SUM(sport_value)" in cleaned


def test_strip_sch_id_keeps_school_sql():
    ctx = UserContext(
        trace_id="t8",
        user_id=1,
        username="sch",
        role=UserRole.SCHOOL,
        active_sch_id=1140,
        bound_sch_ids=[1140],
    )
    sql = "SELECT COUNT(*) FROM sport_activity_qzs_record WHERE sch_id = :sch_id"
    assert strip_sch_id_for_broad_roles(sql, ctx, settings=_settings_sch_on()) == sql


def test_sql_generation_constraints_include_join_aliases():
    ctx = UserContext(trace_id="t9", user_id=1, username="admin", role=UserRole.ADMIN)
    lines = build_llm_sql_generation_constraints(ctx)
    joined = "\n".join(lines)
    assert "短别名" in joined
    assert "禁止裸写字段名" in joined
    assert "允许查询的业务表" in joined
    assert "候选表字段清单" in joined
    assert "sport_activity_qzs_record" not in joined
