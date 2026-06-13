"""POLICY_SCH_ID_ENABLED 特性开关单元测试（第 7 周 · §11.7.1）。"""

import pytest

from app.core.context import UserContext, UserRole
from app.policy.role_policy import applies_sch_id_filter, strip_sch_id_for_broad_roles
from app.sql.guard import SqlGuardError, validate_sql
from config.settings import Settings


def _settings(*, sch_enabled: bool) -> Settings:
    return Settings(
        JWT_SECRET="test-secret",
        POLICY_SCH_ID_ENABLED=sch_enabled,
    )


def _school_ctx() -> UserContext:
    return UserContext(
        trace_id="t",
        user_id=1,
        username="sch",
        role=UserRole.SCHOOL,
        active_sch_id=1140,
        bound_sch_ids=[1140],
    )


def test_school_no_sch_filter_when_flag_off():
    """development 默认关闭时学校账户不强制 sch_id。"""
    ctx = _school_ctx()
    assert applies_sch_id_filter(ctx, settings=_settings(sch_enabled=False)) is False


def test_school_has_sch_filter_when_flag_on():
    ctx = _school_ctx()
    assert applies_sch_id_filter(ctx, settings=_settings(sch_enabled=True)) is True


def test_validate_sql_school_ok_without_sch_id_when_flag_off():
    """关闭 Flag 后学校 SQL 无 sch_id 仍通过校验。"""
    sql = validate_sql(
        "SELECT COUNT(*) FROM sport_activity_qzs_record",
        _school_ctx(),
        max_rows=100,
        settings=_settings(sch_enabled=False),
    )
    assert "LIMIT" in sql.upper()
    assert "sch_id" not in sql.lower()


def test_validate_sql_school_still_requires_sch_id_when_flag_on():
    with pytest.raises(SqlGuardError) as exc:
        validate_sql(
            "SELECT COUNT(*) FROM sport_activity_qzs_record",
            _school_ctx(),
            max_rows=100,
            settings=_settings(sch_enabled=True),
        )
    assert exc.value.code == "MISSING_SCH_ID"


def test_strip_sch_id_for_school_when_flag_off():
    """Flag 关闭时学校账户也移除误加的 :sch_id。"""
    ctx = _school_ctx()
    sql = (
        "SELECT SUM(sport_value) FROM sport_activity_qzs_record "
        "WHERE sch_id = :sch_id LIMIT 5000"
    )
    cleaned = strip_sch_id_for_broad_roles(sql, ctx, settings=_settings(sch_enabled=False))
    assert ":sch_id" not in cleaned.lower()
