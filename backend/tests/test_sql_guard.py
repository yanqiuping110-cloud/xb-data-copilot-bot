"""sql_guard 单元测试。"""

import pytest

from app.core.context import UserContext, UserRole
from app.policy.effective_policy import EffectivePolicy
from app.sql.guard import SqlGuardError, validate_sql
from config.settings import Settings


def _ctx(role: UserRole, active_sch_id: int | None = None) -> UserContext:
    return UserContext(
        trace_id="t",
        user_id=1,
        username="u",
        role=role,
        active_sch_id=active_sch_id,
        bound_sch_ids=[1140] if role == UserRole.SCHOOL else [],
    )


def _settings_sch_on() -> Settings:
    return Settings(JWT_SECRET="test-secret", POLICY_SCH_ID_ENABLED=True)


def test_validate_select_ok():
    """合法 SELECT 应通过并追加 LIMIT。"""
    sql = validate_sql(
        "SELECT COUNT(*) AS cnt FROM sport_activity_qzs_record",
        _ctx(UserRole.ADMIN),
        max_rows=100,
    )
    assert "LIMIT" in sql.upper()
    assert "sport_activity_qzs_record" in sql


def test_reject_insert():
    """禁止 DML。"""
    with pytest.raises(SqlGuardError) as exc:
        validate_sql("INSERT INTO t VALUES (1)", _ctx(UserRole.ADMIN), max_rows=100)
    assert exc.value.code == "BUSINESS_DML_FORBIDDEN"


def test_reject_unknown_table():
    """表不在白名单应拒绝。"""
    with pytest.raises(SqlGuardError) as exc:
        validate_sql(
            "SELECT * FROM secret_table",
            _ctx(UserRole.ADMIN),
            max_rows=100,
        )
    assert exc.value.code == "TABLE_NOT_ALLOWED"


def test_school_requires_sch_id():
    """学校账户 SQL 必须含 sch_id（POLICY_SCH_ID_ENABLED=true 时）。"""
    with pytest.raises(SqlGuardError) as exc:
        validate_sql(
            "SELECT COUNT(*) FROM sport_activity_qzs_record",
            _ctx(UserRole.SCHOOL, active_sch_id=1140),
            max_rows=100,
            settings=_settings_sch_on(),
        )
    assert exc.value.code == "MISSING_SCH_ID"


def test_school_with_sch_id_ok():
    """学校账户带 sch_id 条件应通过（Flag 开启时）。"""
    sql = validate_sql(
        "SELECT COUNT(*) FROM sport_activity_qzs_record WHERE sch_id = 1140",
        _ctx(UserRole.SCHOOL, active_sch_id=1140),
        max_rows=100,
        settings=_settings_sch_on(),
    )
    assert "sch_id" in sql.lower()


def test_validate_with_cte_ok():
    """WITH ... SELECT 应通过校验并在外层追加 LIMIT。"""
    policy = EffectivePolicy(
        is_admin_bypass=True,
        allowed_tables={"sport_activity_new", "sport_activity_qzs_time"},
    )
    sql = validate_sql(
        """
        WITH punch AS (
            SELECT activity_id, COUNT(*) AS cnt
            FROM sport_activity_qzs_time
            GROUP BY activity_id
        )
        SELECT an.activity_name, p.cnt
        FROM sport_activity_new AS an
        LEFT JOIN punch AS p ON an.id = p.activity_id
        WHERE an.status = 1
        """,
        _ctx(UserRole.ADMIN),
        max_rows=5000,
        policy=policy,
    )
    assert "WITH" in sql.upper()
    assert "LIMIT" in sql.upper()
