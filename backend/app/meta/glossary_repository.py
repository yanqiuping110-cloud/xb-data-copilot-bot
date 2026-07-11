"""术语库 CRUD（copilot_glossary_term）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class GlossaryTermRow:
    id: int
    term: str
    canonical_name: str
    definition: str | None
    ref_type: str
    ref_id: int | None
    scope_role: str | None
    status: int
    created_by: int | None
    created_at: datetime | None
    updated_at: datetime | None


class GlossaryRepository:
    """术语库读写。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_terms(
        self,
        *,
        status: int | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[GlossaryTermRow]:
        where = "deleted = 0"
        params: dict = {"limit": limit, "offset": offset}
        if status is not None:
            where += " AND status = :status"
            params["status"] = status
        result = await self._session.execute(
            text(
                f"""
                SELECT id, term, canonical_name, definition, ref_type, ref_id,
                       scope_role, status, created_by, created_at, updated_at
                FROM copilot_glossary_term
                WHERE {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        return [_map_glossary(r) for r in result.mappings().all()]

    async def list_published_for_recall(
        self,
        *,
        scope_role: str | None = None,
        limit: int = 500,
    ) -> list[GlossaryTermRow]:
        """已发布术语，供问句匹配召回。"""
        params: dict = {"limit": limit}
        role_clause = ""
        if scope_role:
            role_clause = " AND (scope_role IS NULL OR scope_role = :scope_role)"
            params["scope_role"] = scope_role
        result = await self._session.execute(
            text(
                f"""
                SELECT id, term, canonical_name, definition, ref_type, ref_id,
                       scope_role, status, created_by, created_at, updated_at
                FROM copilot_glossary_term
                WHERE deleted = 0 AND status = 1
                {role_clause}
                ORDER BY CHAR_LENGTH(term) DESC, id ASC
                LIMIT :limit
                """
            ),
            params,
        )
        return [_map_glossary(r) for r in result.mappings().all()]

    async def get_term(self, term_id: int) -> GlossaryTermRow | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, term, canonical_name, definition, ref_type, ref_id,
                       scope_role, status, created_by, created_at, updated_at
                FROM copilot_glossary_term
                WHERE id = :id AND deleted = 0
                """
            ),
            {"id": term_id},
        )
        row = result.mappings().first()
        return _map_glossary(row) if row else None

    async def insert_term(
        self,
        *,
        term: str,
        canonical_name: str,
        definition: str | None = None,
        ref_type: str = "concept",
        ref_id: int | None = None,
        scope_role: str | None = None,
        status: int = 0,
        created_by: int | None = None,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO copilot_glossary_term (
                    term, canonical_name, definition, ref_type, ref_id,
                    scope_role, status, created_by, deleted
                ) VALUES (
                    :term, :canonical_name, :definition, :ref_type, :ref_id,
                    :scope_role, :status, :created_by, 0
                )
                """
            ),
            {
                "term": term.strip(),
                "canonical_name": canonical_name.strip(),
                "definition": definition,
                "ref_type": ref_type,
                "ref_id": ref_id,
                "scope_role": scope_role,
                "status": status,
                "created_by": created_by,
            },
        )
        return int(result.lastrowid)

    async def update_term(
        self,
        term_id: int,
        *,
        term: str | None = None,
        canonical_name: str | None = None,
        definition: str | None = None,
        ref_type: str | None = None,
        ref_id: int | None = None,
        scope_role: str | None = None,
        status: int | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE copilot_glossary_term SET
                    term = COALESCE(:term, term),
                    canonical_name = COALESCE(:canonical_name, canonical_name),
                    definition = COALESCE(:definition, definition),
                    ref_type = COALESCE(:ref_type, ref_type),
                    ref_id = COALESCE(:ref_id, ref_id),
                    scope_role = COALESCE(:scope_role, scope_role),
                    status = COALESCE(:status, status)
                WHERE id = :id AND deleted = 0
                """
            ),
            {
                "id": term_id,
                "term": term.strip() if term else None,
                "canonical_name": canonical_name.strip() if canonical_name else None,
                "definition": definition,
                "ref_type": ref_type,
                "ref_id": ref_id,
                "scope_role": scope_role,
                "status": status,
            },
        )

    async def delete_term(self, term_id: int) -> None:
        await self._session.execute(
            text("UPDATE copilot_glossary_term SET deleted = 1 WHERE id = :id"),
            {"id": term_id},
        )


def _map_glossary(row) -> GlossaryTermRow:
    return GlossaryTermRow(
        id=int(row["id"]),
        term=str(row["term"]),
        canonical_name=str(row["canonical_name"]),
        definition=row.get("definition"),
        ref_type=str(row["ref_type"]),
        ref_id=int(row["ref_id"]) if row.get("ref_id") is not None else None,
        scope_role=row.get("scope_role"),
        status=int(row["status"]),
        created_by=int(row["created_by"]) if row.get("created_by") is not None else None,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )
