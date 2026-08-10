"""copilot_llm_model 仓储。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.config_crypto import decrypt_secret, encrypt_secret
from app.system.exceptions import SystemConfigError
from config.settings import Settings, get_settings


@dataclass
class LlmModelRow:
    id: int
    name: str
    provider: str
    api_base: str
    api_key_enc: str | None
    model_name: str
    role: str
    timeout_sec: int
    temperature: float
    extra_json: str | None
    is_default: int
    status: int
    created_at: datetime | None
    updated_at: datetime | None

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key_enc)

    @property
    def extra(self) -> dict[str, Any]:
        if not self.extra_json:
            return {}
        try:
            data = json.loads(self.extra_json)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def decrypt_api_key(self, settings: Settings | None = None) -> str:
        return decrypt_secret(self.api_key_enc, settings)


def _map_row(row) -> LlmModelRow:
    return LlmModelRow(
        id=int(row["id"]),
        name=str(row["name"]),
        provider=str(row["provider"]),
        api_base=str(row["api_base"]),
        api_key_enc=row.get("api_key_enc"),
        model_name=str(row["model_name"]),
        role=str(row["role"]),
        timeout_sec=int(row["timeout_sec"] or 120),
        temperature=float(row["temperature"] or 0),
        extra_json=row.get("extra_json"),
        is_default=int(row["is_default"] or 0),
        status=int(row["status"] or 0),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class LlmModelRepository:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self._session = session
        self._settings = settings or get_settings()

    async def count_all(self) -> int:
        result = await self._session.execute(
            text("SELECT COUNT(1) AS c FROM copilot_llm_model WHERE deleted = 0")
        )
        return int(result.mappings().first()["c"])

    async def list_models(self, *, role: str | None = None) -> list[LlmModelRow]:
        sql = """
            SELECT * FROM copilot_llm_model
            WHERE deleted = 0
        """
        params: dict[str, Any] = {}
        if role:
            sql += " AND role = :role"
            params["role"] = role
        sql += " ORDER BY role ASC, is_default DESC, id ASC"
        result = await self._session.execute(text(sql), params)
        return [_map_row(r) for r in result.mappings().all()]

    async def get(self, model_id: int) -> LlmModelRow | None:
        result = await self._session.execute(
            text("SELECT * FROM copilot_llm_model WHERE id = :id AND deleted = 0"),
            {"id": model_id},
        )
        row = result.mappings().first()
        return _map_row(row) if row else None

    async def get_default(self, role: str) -> LlmModelRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT * FROM copilot_llm_model
                WHERE deleted = 0 AND status = 1 AND is_default = 1 AND role = :role
                LIMIT 1
                """
            ),
            {"role": role},
        )
        row = result.mappings().first()
        return _map_row(row) if row else None

    async def insert(
        self,
        *,
        name: str,
        provider: str,
        api_base: str,
        api_key: str | None,
        model_name: str,
        role: str,
        timeout_sec: int,
        temperature: float,
        extra: dict[str, Any] | None,
        is_default: bool,
        status: int,
    ) -> int:
        if role not in ("chat", "embedding"):
            raise SystemConfigError("INVALID_ROLE", "role 仅支持 chat 或 embedding", 400)
        enc = encrypt_secret(api_key or "", self._settings) if api_key is not None else None
        if is_default:
            await self._clear_default(role)
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_llm_model (
                    name, provider, api_base, api_key_enc, model_name, role,
                    timeout_sec, temperature, extra_json, is_default, status
                ) VALUES (
                    :name, :provider, :api_base, :api_key_enc, :model_name, :role,
                    :timeout_sec, :temperature, :extra_json, :is_default, :status
                )
                """
            ),
            {
                "name": name,
                "provider": provider,
                "api_base": api_base,
                "api_key_enc": enc,
                "model_name": model_name,
                "role": role,
                "timeout_sec": timeout_sec,
                "temperature": temperature,
                "extra_json": json.dumps(extra or {}, ensure_ascii=False),
                "is_default": 1 if is_default else 0,
                "status": status,
            },
        )
        return int(result.lastrowid)

    async def update(
        self,
        model_id: int,
        *,
        name: str | None = None,
        provider: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_sec: int | None = None,
        temperature: float | None = None,
        extra: dict[str, Any] | None = None,
        status: int | None = None,
    ) -> None:
        row = await self.get(model_id)
        if row is None:
            raise SystemConfigError("LLM_NOT_FOUND", "模型不存在", 404)
        fields: list[str] = []
        params: dict[str, Any] = {"id": model_id}
        if name is not None:
            fields.append("name = :name")
            params["name"] = name
        if provider is not None:
            fields.append("provider = :provider")
            params["provider"] = provider
        if api_base is not None:
            fields.append("api_base = :api_base")
            params["api_base"] = api_base
        if api_key is not None and api_key.strip() != "":
            fields.append("api_key_enc = :api_key_enc")
            params["api_key_enc"] = encrypt_secret(api_key, self._settings)
        if model_name is not None:
            fields.append("model_name = :model_name")
            params["model_name"] = model_name
        if timeout_sec is not None:
            fields.append("timeout_sec = :timeout_sec")
            params["timeout_sec"] = timeout_sec
        if temperature is not None:
            fields.append("temperature = :temperature")
            params["temperature"] = temperature
        if extra is not None:
            fields.append("extra_json = :extra_json")
            params["extra_json"] = json.dumps(extra, ensure_ascii=False)
        if status is not None:
            fields.append("status = :status")
            params["status"] = status
        if not fields:
            return
        await self._session.execute(
            text(f"UPDATE copilot_llm_model SET {', '.join(fields)} WHERE id = :id AND deleted = 0"),
            params,
        )

    async def soft_delete(self, model_id: int) -> None:
        row = await self.get(model_id)
        if row is None:
            raise SystemConfigError("LLM_NOT_FOUND", "模型不存在", 404)
        if row.is_default == 1:
            others = await self._session.execute(
                text(
                    """
                    SELECT COUNT(1) AS c FROM copilot_llm_model
                    WHERE deleted = 0 AND status = 1 AND role = :role AND id <> :id
                    """
                ),
                {"role": row.role, "id": model_id},
            )
            # 允许删除默认，但若是唯一启用且为默认则拒绝
            if int(others.mappings().first()["c"]) == 0:
                raise SystemConfigError(
                    "LLM_DEFAULT_REQUIRED",
                    "不能删除唯一的默认模型，请先新增并设为默认",
                    400,
                )
        await self._session.execute(
            text("UPDATE copilot_llm_model SET deleted = 1, is_default = 0 WHERE id = :id"),
            {"id": model_id},
        )

    async def set_default(self, model_id: int) -> LlmModelRow:
        row = await self.get(model_id)
        if row is None:
            raise SystemConfigError("LLM_NOT_FOUND", "模型不存在", 404)
        if row.status != 1:
            raise SystemConfigError("LLM_DISABLED", "停用模型不能设为默认", 400)
        await self._clear_default(row.role)
        await self._session.execute(
            text("UPDATE copilot_llm_model SET is_default = 1 WHERE id = :id AND deleted = 0"),
            {"id": model_id},
        )
        updated = await self.get(model_id)
        assert updated is not None
        return updated

    async def _clear_default(self, role: str) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_llm_model SET is_default = 0
                WHERE deleted = 0 AND role = :role AND is_default = 1
                """
            ),
            {"role": role},
        )
