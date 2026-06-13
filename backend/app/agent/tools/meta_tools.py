"""
元数据只读工具：表结构、关系、JOIN 路径（§11.7.2）。
"""

from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.meta.effective import effective_description
from app.meta.repository import MetaRepository, RelationRow
from app.sql.whitelist import get_allowed_tables
from config.settings import Settings


def _table_allowed(table_name: str) -> bool:
    """表白名单校验（工具层与 sql_guard 一致）。"""
    return table_name.lower() in get_allowed_tables()


async def describe_table(
    session: AsyncSession,
    settings: Settings,
    *,
    table: str,
) -> dict[str, Any]:
    """
    返回单表字段清单：meta 人工定义 + 类型/备注。

    数据源：copilot_table_meta + copilot_column_meta（不 probe 业务库）。
    """
    _ = settings
    repo = MetaRepository(session)
    row = await repo.find_table_by_name(table.strip())
    if row is None or row.status != 1:
        return {"error": "TABLE_NOT_FOUND", "table": table}
    if not _table_allowed(row.table_name):
        return {"error": "TABLE_NOT_ALLOWED", "table": row.table_name}

    columns = await repo.list_columns(row.id)
    active_cols = [c for c in columns if c.status == 1]
    return {
        "table": row.table_name,
        "table_role": row.table_role,
        "grain": row.grain,
        "description": effective_description(row.description_manual, row.table_comment_auto),
        "sch_id_column": row.sch_id_column,
        "column_count": len(active_cols),
        "columns": [
            {
                "name": c.column_name,
                "data_type": c.data_type,
                "role": c.column_role,
                "description": c.effective_description,
                "recall_enabled": bool(c.recall_enabled),
            }
            for c in active_cols[:50]
        ],
    }


async def list_relations(
    session: AsyncSession,
    settings: Settings,
    *,
    table: str | None = None,
) -> dict[str, Any]:
    """列出已注册表间 JOIN 关系（copilot_table_relation）。"""
    _ = settings
    repo = MetaRepository(session)
    all_relations = await repo.list_relations()
    allowed = get_allowed_tables()

    filtered: list[RelationRow] = []
    for rel in all_relations:
        if rel.status != 1:
            continue
        if rel.from_table_name not in allowed or rel.to_table_name not in allowed:
            continue
        if table:
            t = table.strip().lower()
            if rel.from_table_name.lower() != t and rel.to_table_name.lower() != t:
                continue
        filtered.append(rel)

    return {
        "table_filter": table,
        "count": len(filtered),
        "relations": [
            {
                "from_table": r.from_table_name,
                "from_column": r.from_column,
                "to_table": r.to_table_name,
                "to_column": r.to_column,
                "relation_type": r.relation_type,
                "join_hint": r.join_hint,
                "cardinality": r.cardinality,
            }
            for r in filtered[:30]
        ],
    }


def _build_relation_adjacency(relations: list[RelationRow]) -> dict[str, list[RelationRow]]:
    """无向邻接表：便于 BFS 求 JOIN 路径。"""
    adj: dict[str, list[RelationRow]] = {}
    for rel in relations:
        if rel.status != 1:
            continue
        adj.setdefault(rel.from_table_name, []).append(rel)
        adj.setdefault(rel.to_table_name, []).append(rel)
    return adj


def _neighbor_table(rel: RelationRow, current: str) -> str:
    if rel.from_table_name == current:
        return rel.to_table_name
    return rel.from_table_name


async def get_join_path(
    session: AsyncSession,
    settings: Settings,
    *,
    from_table: str,
    to_table: str,
) -> dict[str, Any]:
    """
    在 copilot_table_relation 上 BFS 求最短 JOIN 链。

    返回有序边列表，供复杂报表多表关联参考。
    """
    _ = settings
    src = from_table.strip()
    dst = to_table.strip()
    if not _table_allowed(src) or not _table_allowed(dst):
        return {"error": "TABLE_NOT_ALLOWED", "from_table": src, "to_table": dst}
    if src == dst:
        return {"from_table": src, "to_table": dst, "hops": 0, "path": []}

    repo = MetaRepository(session)
    relations = await repo.list_relations()
    allowed = get_allowed_tables()
    relations = [
        r
        for r in relations
        if r.from_table_name in allowed and r.to_table_name in allowed
    ]
    adj = _build_relation_adjacency(relations)

    if src not in adj or dst not in adj:
        return {"error": "NO_PATH", "from_table": src, "to_table": dst}

    queue: deque[str] = deque([src])
    visited = {src}
    parent: dict[str, tuple[str, RelationRow]] = {}

    while queue:
        node = queue.popleft()
        if node == dst:
            break
        for rel in adj.get(node, []):
            nxt = _neighbor_table(rel, node)
            if nxt in visited:
                continue
            visited.add(nxt)
            parent[nxt] = (node, rel)
            queue.append(nxt)

    if dst not in parent and dst != src:
        return {"error": "NO_PATH", "from_table": src, "to_table": dst}

    path_edges: list[dict[str, Any]] = []
    cur = dst
    while cur != src:
        prev, rel = parent[cur]
        path_edges.append(
            {
                "from_table": rel.from_table_name,
                "from_column": rel.from_column,
                "to_table": rel.to_table_name,
                "to_column": rel.to_column,
                "join_hint": rel.join_hint,
            }
        )
        cur = prev
    path_edges.reverse()

    return {
        "from_table": src,
        "to_table": dst,
        "hops": len(path_edges),
        "path": path_edges,
    }
