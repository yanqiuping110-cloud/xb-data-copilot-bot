"""系统参数校验与 SQL LIMIT 运行时回退（不依赖 MySQL）。"""

from __future__ import annotations

import pytest

from app.system.exceptions import SystemConfigError
from app.system.param_repository import normalize_param_value, require_spec
from app.system.param_specs import PARAM_SQL_MAX_ROWS, SYS_PARAM_SPECS, clamp_sql_max_rows
from app.system.runtime_config import invalidate_runtime_cache, resolve_sql_max_rows
from config.settings import Settings


def test_sql_max_rows_settings_default_is_100():
    s = Settings(JWT_SECRET="test-secret-for-sql-max-rows-default")
    assert s.sql_max_rows == 100


def test_clamp_sql_max_rows():
    assert clamp_sql_max_rows(1) == 1
    assert clamp_sql_max_rows(100) == 100
    assert clamp_sql_max_rows(0) == 1
    assert clamp_sql_max_rows(99999) == 10000


def test_normalize_sql_max_rows_ok():
    spec = SYS_PARAM_SPECS[PARAM_SQL_MAX_ROWS]
    assert normalize_param_value(spec, "100") == "100"
    assert normalize_param_value(spec, " 50 ") == "50"


def test_normalize_sql_max_rows_rejects_non_int():
    spec = SYS_PARAM_SPECS[PARAM_SQL_MAX_ROWS]
    with pytest.raises(SystemConfigError) as exc:
        normalize_param_value(spec, "abc")
    assert exc.value.code == "INVALID_PARAM_VALUE"


def test_normalize_sql_max_rows_rejects_out_of_range():
    spec = SYS_PARAM_SPECS[PARAM_SQL_MAX_ROWS]
    with pytest.raises(SystemConfigError):
        normalize_param_value(spec, "0")
    with pytest.raises(SystemConfigError):
        normalize_param_value(spec, "10001")


def test_require_spec_unknown():
    with pytest.raises(SystemConfigError) as exc:
        require_spec("not_a_real_param")
    assert exc.value.code == "UNKNOWN_SYS_PARAM"


def test_resolve_sql_max_rows_falls_back_to_settings():
    invalidate_runtime_cache()
    settings = Settings(JWT_SECRET="test-secret-resolve-limit", SQL_MAX_ROWS=80)
    assert resolve_sql_max_rows(settings) == 80
