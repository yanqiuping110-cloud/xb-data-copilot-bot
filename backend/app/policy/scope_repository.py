"""
DataScope 仓储：维度、绑定、grant、列 deny（第 13 周）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ScopeRepository:
    """copilot 库 DataScope 表读写。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_data_grants(self, user_id: int) -> dict[str, list[Any]]:
        result = await self._session.execute(
            text(
                """
                SELECT dimension_code, operator, values_json
                FROM copilot_user_data_grant
                WHERE user_id = :user_id AND deleted = 0
                """
            ),
            {"user_id": user_id},
        )
        grants: dict[str, list[Any]] = {}
        for row in result.mappings():
            op = row.get("operator") or "in"
            if op == "all":
                continue
            raw = row.get("values_json") or "[]"
            try:
                values = json.loads(raw) if isinstance(raw, str) else list(raw)
            except (json.JSONDecodeError, TypeError):
                values = []
            if values:
                grants[row["dimension_code"]] = values
        return grants

    async def load_table_grants(self, user_id: int) -> frozenset[str]:
        result = await self._session.execute(
            text(
                """
                SELECT table_name FROM copilot_user_table_grant
                WHERE user_id = :user_id AND deleted = 0 AND effect = 'allow'
                """
            ),
            {"user_id": user_id},
        )
        return frozenset(row["table_name"].lower() for row in result.mappings() if row.get("table_name"))

    async def load_table_bindings(self) -> dict[str, list[tuple[str, str]]]:
        """
        物理表名（小写）→ [(dimension_code, column_name)]。

        仅保留「绑定列在 copilot_column_meta 中真实存在」的条目，
        避免对无 sch_id 的维度表误注入（Unknown column）。
        """
        result = await self._session.execute(
            text(
                """
                SELECT LOWER(tm.table_name) AS table_name,
                       b.dimension_code, b.column_name
                FROM copilot_table_scope_binding b
                JOIN copilot_table_meta tm
                  ON tm.id = b.table_id AND tm.deleted = 0 AND tm.status = 1
                WHERE b.deleted = 0
                  AND EXISTS (
                    SELECT 1
                    FROM copilot_column_meta c
                    WHERE c.table_id = tm.id
                      AND c.deleted = 0
                      AND c.status = 1
                      AND LOWER(c.column_name) = LOWER(b.column_name)
                  )
                """
            ),
        )
        bindings: dict[str, list[tuple[str, str]]] = {}
        for row in result.mappings():
            tname = row["table_name"]
            bindings.setdefault(tname, []).append((row["dimension_code"], row["column_name"]))
        return bindings

    async def load_denied_columns(self, user_id: int) -> dict[str, frozenset[str]]:
        result = await self._session.execute(
            text(
                """
                SELECT LOWER(table_name) AS table_name, column_name
                FROM copilot_column_deny
                WHERE deleted = 0 AND (user_id IS NULL OR user_id = :user_id)
                """
            ),
            {"user_id": user_id},
        )
        denied: dict[str, set[str]] = {}
        for row in result.mappings():
            tname = row["table_name"]
            denied.setdefault(tname, set()).add(row["column_name"])
        return {k: frozenset(v) for k, v in denied.items()}
