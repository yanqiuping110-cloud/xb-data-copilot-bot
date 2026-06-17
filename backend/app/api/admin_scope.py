"""
DataScope 管理 API（第 13 周 · ADMIN）。

路径前缀：/api/v1/admin/meta/scope-* 与 /api/v1/admin/users/{id}/grants
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.security import require_admin, require_meta_manager
from app.db.copilot import get_copilot_session

router = APIRouter(tags=["admin-scope"])


class ScopeDimensionBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    value_type: str = Field(default="int", pattern="^(int|string)$")
    status: int = Field(default=1, ge=0, le=1)


class DataGrantsBody(BaseModel):
    grants: dict[str, list[Any]] = Field(
        default_factory=dict,
        description="dimension_code → 允许值列表",
    )


class TableGrantsBody(BaseModel):
    table_names: list[str] = Field(default_factory=list)


class ColumnDenyBody(BaseModel):
    table_name: str
    column_name: str
    reason: str | None = None
    user_id: int | None = None


class ScopeBindingBody(BaseModel):
    dimension_code: str
    column_name: str


@router.get("/api/v1/admin/meta/scope-dimensions")
async def list_scope_dimensions(
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """列出已注册范围维度。"""
    result = await session.execute(
        text(
            """
            SELECT code, display_name, value_type, status
            FROM copilot_scope_dimension WHERE deleted = 0
            ORDER BY code
            """
        )
    )
    return {"items": [dict(row) for row in result.mappings()]}


@router.post("/api/v1/admin/meta/scope-dimensions")
async def create_scope_dimension(
    body: ScopeDimensionBody,
    admin: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """注册范围维度。"""
    await session.execute(
        text(
            """
            INSERT INTO copilot_scope_dimension (code, display_name, value_type, status)
            VALUES (:code, :display_name, :value_type, :status)
            ON DUPLICATE KEY UPDATE
                display_name = VALUES(display_name),
                value_type = VALUES(value_type),
                status = VALUES(status),
                deleted = 0,
                updated_at = NOW()
            """
        ),
        body.model_dump(),
    )
    await session.commit()
    return {"ok": True, "code": body.code}


@router.put("/api/v1/admin/users/{user_id}/data-grants")
async def put_user_data_grants(
    user_id: int,
    body: DataGrantsBody,
    admin: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """覆盖用户行级数据授权。"""
    await session.execute(
        text("UPDATE copilot_user_data_grant SET deleted = 1 WHERE user_id = :uid"),
        {"uid": user_id},
    )
    for dim_code, values in body.grants.items():
        await session.execute(
            text(
                """
                INSERT INTO copilot_user_data_grant (
                    user_id, dimension_code, operator, values_json, created_by
                ) VALUES (:uid, :dim, 'in', :vals, :by)
                """
            ),
            {
                "uid": user_id,
                "dim": dim_code,
                "vals": json.dumps(values, ensure_ascii=False),
                "by": admin.user_id,
            },
        )
    await session.commit()
    return {"ok": True, "userId": user_id, "grants": body.grants}


@router.put("/api/v1/admin/users/{user_id}/table-grants")
async def put_user_table_grants(
    user_id: int,
    body: TableGrantsBody,
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """覆盖用户表级 allow 列表。"""
    await session.execute(
        text("UPDATE copilot_user_table_grant SET deleted = 1 WHERE user_id = :uid"),
        {"uid": user_id},
    )
    for tname in body.table_names:
        await session.execute(
            text(
                """
                INSERT INTO copilot_user_table_grant (user_id, table_name, effect)
                VALUES (:uid, :tname, 'allow')
                """
            ),
            {"uid": user_id, "tname": tname},
        )
    await session.commit()
    return {"ok": True, "userId": user_id, "tables": body.table_names}


@router.get("/api/v1/admin/users/{user_id}/grants")
async def get_user_grants(
    user_id: int,
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """汇总用户 data/table grant。"""
    from app.policy.scope_repository import ScopeRepository

    repo = ScopeRepository(session)
    return {
        "userId": user_id,
        "dataGrants": await repo.load_data_grants(user_id),
        "tableGrants": sorted(await repo.load_table_grants(user_id)),
    }


@router.get("/api/v1/admin/meta/column-deny")
async def list_column_deny(
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """列出全局与用户级列 deny 规则。"""
    result = await session.execute(
        text(
            """
            SELECT id, user_id, table_name, column_name, reason
            FROM copilot_column_deny
            WHERE deleted = 0
            ORDER BY table_name, column_name
            """
        ),
    )
    return {
        "items": [
            {
                "id": row["id"],
                "userId": row["user_id"],
                "tableName": row["table_name"],
                "columnName": row["column_name"],
                "reason": row["reason"],
            }
            for row in result.mappings()
        ]
    }


@router.post("/api/v1/admin/meta/column-deny")
async def add_column_deny(
    body: ColumnDenyBody,
    _: Annotated[UserContext, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """新增列 deny 规则。"""
    await session.execute(
        text(
            """
            INSERT INTO copilot_column_deny (user_id, table_name, column_name, reason)
            VALUES (:user_id, :table_name, :column_name, :reason)
            """
        ),
        body.model_dump(),
    )
    await session.commit()
    return {"ok": True}


@router.get("/api/v1/admin/meta/tables/{table_id}/scope-bindings")
async def get_table_scope_bindings(
    table_id: int,
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """查询表的维度列绑定。"""
    result = await session.execute(
        text(
            """
            SELECT dimension_code, column_name
            FROM copilot_table_scope_binding
            WHERE table_id = :tid AND deleted = 0
            ORDER BY dimension_code
            """
        ),
        {"tid": table_id},
    )
    return {
        "items": [
            {"dimensionCode": row["dimension_code"], "columnName": row["column_name"]}
            for row in result.mappings()
        ]
    }


@router.put("/api/v1/admin/meta/tables/{table_id}/scope-bindings")
async def put_table_scope_bindings(
    table_id: int,
    bindings: list[ScopeBindingBody],
    _: Annotated[UserContext, Depends(require_meta_manager)],
    session: Annotated[AsyncSession, Depends(get_copilot_session)],
):
    """覆盖表的维度列绑定。"""
    await session.execute(
        text(
            "UPDATE copilot_table_scope_binding SET deleted = 1 WHERE table_id = :tid"
        ),
        {"tid": table_id},
    )
    for b in bindings:
        await session.execute(
            text(
                """
                INSERT INTO copilot_table_scope_binding (table_id, dimension_code, column_name)
                VALUES (:tid, :dim, :col)
                """
            ),
            {"tid": table_id, "dim": b.dimension_code, "col": b.column_name},
        )
    await session.commit()
    return {"ok": True, "tableId": table_id, "count": len(bindings)}
