"""系统参数目录：键、类型、校验范围、默认值。"""

from __future__ import annotations

from dataclasses import dataclass


PARAM_SQL_MAX_ROWS = "sql_max_rows"


@dataclass(frozen=True)
class SysParamSpec:
    key: str
    display_name: str
    description: str
    value_type: str  # int | string | bool
    default: str
    min_value: int | None = None
    max_value: int | None = None


SYS_PARAM_SPECS: dict[str, SysParamSpec] = {
    PARAM_SQL_MAX_ROWS: SysParamSpec(
        key=PARAM_SQL_MAX_ROWS,
        display_name="问数 SQL 默认 LIMIT",
        description="查询执行时强制附加的最大行数；模型写出更大 LIMIT 也会被压到此值。",
        value_type="int",
        default="100",
        min_value=1,
        max_value=10000,
    ),
}


def get_param_spec(key: str) -> SysParamSpec | None:
    return SYS_PARAM_SPECS.get(key)


def clamp_sql_max_rows(value: int) -> int:
    spec = SYS_PARAM_SPECS[PARAM_SQL_MAX_ROWS]
    lo = spec.min_value if spec.min_value is not None else 1
    hi = spec.max_value if spec.max_value is not None else 10000
    return max(lo, min(hi, int(value)))
