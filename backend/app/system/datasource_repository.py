"""copilot_business_datasource 仓储。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.config_crypto import decrypt_secret, encrypt_secret
from app.system.exceptions import SystemConfigError
from config.settings import Settings, get_settings


@dataclass
class DatasourceRow:
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    password_enc: str | None
    is_default: int
    status: int
    last_test_at: datetime | None
    last_test_ok: int | None
    created_at: datetime | None
    updated_at: datetime | None
    options_json: str | None = None
    server_version: str | None = None
    version_checked_at: datetime | None = None

    @property
    def has_password(self) -> bool:
        return bool(self.password_enc)

    def decrypt_password(self, settings: Settings | None = None) -> str:
        return decrypt_secret(self.password_enc, settings)

    def options(self) -> dict[str, Any]:
        if not self.options_json:
            return {}
        import json

        try:
            data = json.loads(self.options_json)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _map_row(row) -> DatasourceRow:
    return DatasourceRow(
        id=int(row["id"]),
        name=str(row["name"]),
        db_type=str(row["db_type"] or "mysql"),
        host=str(row["host"]),
        port=int(row["port"] or 3306),
        database_name=str(row["database_name"]),
        username=str(row["username"]),
        password_enc=row.get("password_enc"),
        is_default=int(row["is_default"] or 0),
        status=int(row["status"] or 0),
        last_test_at=row.get("last_test_at"),
        last_test_ok=None if row.get("last_test_ok") is None else int(row["last_test_ok"]),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        options_json=row.get("options_json"),
        server_version=row.get("server_version"),
        version_checked_at=row.get("version_checked_at"),
    )


class DatasourceRepository:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self._session = session
        self._settings = settings or get_settings()

    async def count_all(self) -> int:
        result = await self._session.execute(
            text("SELECT COUNT(1) AS c FROM copilot_business_datasource WHERE deleted = 0")
        )
        return int(result.mappings().first()["c"])

    async def list_all(self) -> list[DatasourceRow]:
        result = await self._session.execute(
            text(
                """
                SELECT * FROM copilot_business_datasource
                WHERE deleted = 0
                ORDER BY is_default DESC, id ASC
                """
            )
        )
        return [_map_row(r) for r in result.mappings().all()]

    async def get(self, ds_id: int) -> DatasourceRow | None:
        result = await self._session.execute(
            text("SELECT * FROM copilot_business_datasource WHERE id = :id AND deleted = 0"),
            {"id": ds_id},
        )
        row = result.mappings().first()
        return _map_row(row) if row else None

    async def get_default(self) -> DatasourceRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT * FROM copilot_business_datasource
                WHERE deleted = 0 AND status = 1 AND is_default = 1
                LIMIT 1
                """
            )
        )
        row = result.mappings().first()
        return _map_row(row) if row else None

    async def insert(
        self,
        *,
        name: str,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str | None,
        is_default: bool,
        status: int,
    ) -> int:
        from app.system.catalog_loader import get_datasource_type, is_datasource_selectable

        meta = get_datasource_type(db_type)
        if meta is None or not is_datasource_selectable(db_type):
            label = (meta or {}).get("name") or db_type
            raise SystemConfigError(
                "UNSUPPORTED_DB_TYPE",
                f"数据源类型「{label}」暂不可用，请从 Catalog 可选类型中选择",
                400,
            )
        enc = encrypt_secret(password or "", self._settings) if password is not None else None
        if is_default:
            await self._clear_default()
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_business_datasource (
                    name, db_type, host, port, database_name, username, password_enc,
                    is_default, status
                ) VALUES (
                    :name, :db_type, :host, :port, :database_name, :username, :password_enc,
                    :is_default, :status
                )
                """
            ),
            {
                "name": name,
                "db_type": db_type,
                "host": host,
                "port": port,
                "database_name": database_name,
                "username": username,
                "password_enc": enc,
                "is_default": 1 if is_default else 0,
                "status": status,
            },
        )
        return int(result.lastrowid)

    async def update(
        self,
        ds_id: int,
        *,
        name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        database_name: str | None = None,
        username: str | None = None,
        password: str | None = None,
        status: int | None = None,
    ) -> None:
        row = await self.get(ds_id)
        if row is None:
            raise SystemConfigError("DATASOURCE_NOT_FOUND", "数据源不存在", 404)
        fields: list[str] = []
        params: dict[str, Any] = {"id": ds_id}
        if name is not None:
            fields.append("name = :name")
            params["name"] = name
        if host is not None:
            fields.append("host = :host")
            params["host"] = host
        if port is not None:
            fields.append("port = :port")
            params["port"] = port
        if database_name is not None:
            fields.append("database_name = :database_name")
            params["database_name"] = database_name
        if username is not None:
            fields.append("username = :username")
            params["username"] = username
        if password is not None and password.strip() != "":
            fields.append("password_enc = :password_enc")
            params["password_enc"] = encrypt_secret(password, self._settings)
        if status is not None:
            fields.append("status = :status")
            params["status"] = status
        if not fields:
            return
        await self._session.execute(
            text(
                f"UPDATE copilot_business_datasource SET {', '.join(fields)} "
                "WHERE id = :id AND deleted = 0"
            ),
            params,
        )

    async def soft_delete(self, ds_id: int) -> None:
        row = await self.get(ds_id)
        if row is None:
            raise SystemConfigError("DATASOURCE_NOT_FOUND", "数据源不存在", 404)
        if row.is_default == 1:
            others = await self._session.execute(
                text(
                    """
                    SELECT COUNT(1) AS c FROM copilot_business_datasource
                    WHERE deleted = 0 AND status = 1 AND id <> :id
                    """
                ),
                {"id": ds_id},
            )
            if int(others.mappings().first()["c"]) == 0:
                raise SystemConfigError(
                    "DATASOURCE_DEFAULT_REQUIRED",
                    "不能删除唯一的默认数据源，请先新增并设为默认",
                    400,
                )
        await self._session.execute(
            text(
                "UPDATE copilot_business_datasource SET deleted = 1, is_default = 0 WHERE id = :id"
            ),
            {"id": ds_id},
        )

    async def set_default(self, ds_id: int) -> DatasourceRow:
        row = await self.get(ds_id)
        if row is None:
            raise SystemConfigError("DATASOURCE_NOT_FOUND", "数据源不存在", 404)
        if row.status != 1:
            raise SystemConfigError("DATASOURCE_DISABLED", "停用数据源不能设为默认", 400)
        await self._clear_default()
        await self._session.execute(
            text(
                "UPDATE copilot_business_datasource SET is_default = 1 WHERE id = :id AND deleted = 0"
            ),
            {"id": ds_id},
        )
        updated = await self.get(ds_id)
        assert updated is not None
        return updated

    async def update_test_result(
        self,
        ds_id: int,
        *,
        ok: bool,
        server_version: str | None = None,
    ) -> None:
        params: dict[str, Any] = {"id": ds_id, "ok": 1 if ok else 0}
        if server_version is not None:
            try:
                await self._session.execute(
                    text(
                        """
                        UPDATE copilot_business_datasource
                        SET last_test_at = NOW(), last_test_ok = :ok,
                            server_version = :server_version, version_checked_at = NOW()
                        WHERE id = :id AND deleted = 0
                        """
                    ),
                    {**params, "server_version": server_version[:128]},
                )
                return
            except Exception:
                # V017 未执行时降级为仅写测试结果
                pass
        await self._session.execute(
            text(
                """
                UPDATE copilot_business_datasource
                SET last_test_at = NOW(), last_test_ok = :ok
                WHERE id = :id AND deleted = 0
                """
            ),
            params,
        )

    async def _clear_default(self) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_business_datasource SET is_default = 0
                WHERE deleted = 0 AND is_default = 1
                """
            )
        )
