"""copilot_sys_param 仓储。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.system.exceptions import SystemConfigError
from app.system.param_specs import SysParamSpec, get_param_spec


@dataclass
class SysParamRow:
    id: int
    param_key: str
    param_value: str
    value_type: str
    display_name: str
    description: str | None
    min_value: int | None
    max_value: int | None
    updated_by: int | None
    created_at: datetime | None
    updated_at: datetime | None


def _map_row(row) -> SysParamRow:
    return SysParamRow(
        id=int(row["id"]),
        param_key=str(row["param_key"]),
        param_value=str(row["param_value"]),
        value_type=str(row["value_type"] or "string"),
        display_name=str(row["display_name"]),
        description=row.get("description"),
        min_value=row.get("min_value"),
        max_value=row.get("max_value"),
        updated_by=row.get("updated_by"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def normalize_param_value(spec: SysParamSpec, raw: str) -> str:
    text_val = (raw or "").strip()
    if spec.value_type == "int":
        try:
            n = int(text_val)
        except (TypeError, ValueError) as exc:
            raise SystemConfigError(
                "INVALID_PARAM_VALUE",
                f"「{spec.display_name}」须为整数",
                400,
            ) from exc
        if spec.min_value is not None and n < spec.min_value:
            raise SystemConfigError(
                "INVALID_PARAM_VALUE",
                f"「{spec.display_name}」不能小于 {spec.min_value}",
                400,
            )
        if spec.max_value is not None and n > spec.max_value:
            raise SystemConfigError(
                "INVALID_PARAM_VALUE",
                f"「{spec.display_name}」不能大于 {spec.max_value}",
                400,
            )
        return str(n)
    if spec.value_type == "bool":
        lowered = text_val.lower()
        if lowered in ("1", "true", "yes", "on"):
            return "true"
        if lowered in ("0", "false", "no", "off"):
            return "false"
        raise SystemConfigError(
            "INVALID_PARAM_VALUE",
            f"「{spec.display_name}」须为 true/false",
            400,
        )
    if not text_val:
        raise SystemConfigError(
            "INVALID_PARAM_VALUE",
            f"「{spec.display_name}」不能为空",
            400,
        )
    return text_val


class SysParamRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[SysParamRow]:
        result = await self._session.execute(
            text(
                """
                SELECT id, param_key, param_value, value_type, display_name, description,
                       min_value, max_value, updated_by, created_at, updated_at
                FROM copilot_sys_param
                WHERE deleted = 0
                ORDER BY id ASC
                """
            )
        )
        return [_map_row(row) for row in result.mappings().all()]

    async def get_by_key(self, param_key: str) -> SysParamRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, param_key, param_value, value_type, display_name, description,
                       min_value, max_value, updated_by, created_at, updated_at
                FROM copilot_sys_param
                WHERE param_key = :k AND deleted = 0
                LIMIT 1
                """
            ),
            {"k": param_key},
        )
        row = result.mappings().first()
        return _map_row(row) if row else None

    async def upsert(
        self,
        *,
        spec: SysParamSpec,
        value: str,
        updated_by: int | None,
    ) -> SysParamRow:
        normalized = normalize_param_value(spec, value)
        existing = await self.get_by_key(spec.key)
        if existing is None:
            await self._session.execute(
                text(
                    """
                    INSERT INTO copilot_sys_param (
                        param_key, param_value, value_type, display_name, description,
                        min_value, max_value, updated_by
                    ) VALUES (
                        :k, :v, :vt, :dn, :ds, :lo, :hi, :ub
                    )
                    """
                ),
                {
                    "k": spec.key,
                    "v": normalized,
                    "vt": spec.value_type,
                    "dn": spec.display_name,
                    "ds": spec.description,
                    "lo": spec.min_value,
                    "hi": spec.max_value,
                    "ub": updated_by,
                },
            )
        else:
            await self._session.execute(
                text(
                    """
                    UPDATE copilot_sys_param
                    SET param_value = :v,
                        value_type = :vt,
                        display_name = :dn,
                        description = :ds,
                        min_value = :lo,
                        max_value = :hi,
                        updated_by = :ub
                    WHERE param_key = :k AND deleted = 0
                    """
                ),
                {
                    "k": spec.key,
                    "v": normalized,
                    "vt": spec.value_type,
                    "dn": spec.display_name,
                    "ds": spec.description,
                    "lo": spec.min_value,
                    "hi": spec.max_value,
                    "ub": updated_by,
                },
            )
        row = await self.get_by_key(spec.key)
        assert row is not None
        return row


def require_spec(param_key: str) -> SysParamSpec:
    spec = get_param_spec(param_key)
    if spec is None:
        raise SystemConfigError("UNKNOWN_SYS_PARAM", f"未知系统参数：{param_key}", 404)
    return spec
