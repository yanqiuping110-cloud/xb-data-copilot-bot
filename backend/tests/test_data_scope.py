"""DataScope：EffectivePolicy 与 ScopeInjector 单元测试。"""

import pytest

from app.core.context import UserContext, UserRole
from app.policy.effective_policy import EffectivePolicy, build_scope_prompt_sections
from app.policy.scope_injector import apply_scope_to_sql, validate_scope_literals
from app.sql.column_guard import validate_denied_columns_sql
from app.sql.guard import SqlGuardError, validate_sql
from config.settings import Settings


def _admin_ctx() -> UserContext:
    return UserContext(trace_id="t", user_id=1, username="admin", role=UserRole.ADMIN)


def _policy_fixture() -> EffectivePolicy:
    return EffectivePolicy(
        data_grants={"tenant": [10, 20]},
        table_bindings={
            "fact_orders": [("tenant", "tenant_id")],
        },
        allowed_tables=frozenset({"fact_orders"}),
        denied_columns={"fact_orders": frozenset({"secret_col"})},
        scope_sql_hints="维度 tenant 允许 10,20",
        is_admin_bypass=False,
    )


def test_build_scope_prompt_sections():
    text = build_scope_prompt_sections(_policy_fixture())
    assert "【数据范围】" in text
    assert "【可见表】" in text
    assert "secret_col" in text or "【禁止字段】" in text


def test_apply_scope_injects_in_clause():
    policy = _policy_fixture()
    sql = "SELECT COUNT(*) AS cnt FROM fact_orders"
    scoped, params = apply_scope_to_sql(sql, policy)
    assert "tenant_id in" in scoped.lower()
    assert "scope_tenant_0" in params
    assert params["scope_tenant_0"] == 10


def test_apply_scope_only_on_tables_with_binding():
    """JOIN 时只对有 school 绑定的事实表注入，不对无 sch_id 的维度表注入。"""
    policy = EffectivePolicy(
        data_grants={"school": [1, 2, 3]},
        table_bindings={
            "sport_activity_qzs_time": [("school", "sch_id")],
        },
        allowed_tables=frozenset({"sport_activity_qzs_time", "sport_activity_new"}),
        is_admin_bypass=False,
    )
    sql = (
        "SELECT a.record_date AS `日期`, COUNT(DISTINCT a.user_id) AS `活动参与人数` "
        "FROM sport_activity_qzs_time AS a "
        "JOIN sport_activity_new AS act ON a.activity_id = act.id AND act.status = 1 "
        "WHERE a.record_date >= CURRENT_DATE - INTERVAL '30' DAY "
        "GROUP BY a.record_date"
    )
    scoped, params = apply_scope_to_sql(sql, policy)
    assert "a.sch_id" in scoped.lower()
    assert "act.sch_id" not in scoped.lower()
    assert params == {"scope_school_0": 1, "scope_school_1": 2, "scope_school_2": 3}


def test_validate_denied_column():
    policy = _policy_fixture()
    with pytest.raises(SqlGuardError) as exc:
        validate_denied_columns_sql(
            "SELECT secret_col FROM fact_orders",
            policy.denied_columns,
        )
    assert exc.value.code == "COLUMN_DENIED"


def test_validate_sql_respects_policy_allowed_tables():
    policy = EffectivePolicy(
        allowed_tables=frozenset({"fact_orders"}),
        is_admin_bypass=False,
    )
    settings = Settings(JWT_SECRET="test-secret")
    sql = validate_sql(
        "SELECT 1 FROM fact_orders",
        _admin_ctx(),
        max_rows=10,
        settings=settings,
        policy=policy,
    )
    assert "fact_orders" in sql.lower()

    with pytest.raises(SqlGuardError) as exc:
        validate_sql(
            "SELECT 1 FROM other_table",
            _admin_ctx(),
            max_rows=10,
            settings=settings,
            policy=policy,
        )
    assert exc.value.code == "TABLE_NOT_ALLOWED"


def test_reject_delete_via_guard():
    with pytest.raises(SqlGuardError) as exc:
        validate_sql(
            "DELETE FROM fact_orders",
            _admin_ctx(),
            max_rows=10,
            settings=Settings(JWT_SECRET="test-secret"),
        )
    assert exc.value.code == "BUSINESS_DML_FORBIDDEN"
