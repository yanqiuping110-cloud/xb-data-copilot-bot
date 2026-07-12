"""
Plan 结构分析：检测多来源表经同一汇聚表、彼此无直连时的拆分策略。

不依赖「事实表/维表」术语，仅用表关系图 + 可选字段描述推断。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.meta.repository import ColumnMetaRow, RelationRow, TableMetaRow

_AGGREGATE_STRATEGY_SUBQUERY = "subquery_per_branch"
_QUERY_SHAPE_MULTI_BRANCH = "multi_branch_aggregate"

_SOURCE_ROLES = frozenset({"fact", "detail", "transaction", "event"})


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _is_n_to_one(cardinality: str | None) -> bool:
    if not cardinality:
        return False
    return "n:1" in cardinality.replace(" ", "").lower()


def _build_adjacency(relations: list[RelationRow]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for rel in relations:
        if rel.status != 1:
            continue
        a = rel.from_table_name
        b = rel.to_table_name
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _has_path(start: str, end: str, adj: dict[str, set[str]]) -> bool:
    if start == end:
        return True
    if start not in adj or end not in adj:
        return False
    seen = {start}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for nb in adj.get(node, ()):
            if nb in seen:
                continue
            if nb == end:
                return True
            seen.add(nb)
            queue.append(nb)
    return False


def _has_path_avoiding_anchor(
    start: str,
    end: str,
    adj: dict[str, set[str]],
    anchor: str,
) -> bool:
    """
    两来源表是否经「非汇聚表」路径连通。

    仅通过同一汇聚表相连（hub-spoke）视为不连通，仍需分路聚合。
    """
    if start == end:
        return True
    anchor_norm = _normalize_name(anchor)
    if _normalize_name(start) == anchor_norm or _normalize_name(end) == anchor_norm:
        return False
    seen = {_normalize_name(start)}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for nb in adj.get(node, ()):
            if _normalize_name(nb) == anchor_norm:
                continue
            key = _normalize_name(nb)
            if key in seen:
                continue
            if _normalize_name(nb) == _normalize_name(end):
                return True
            seen.add(key)
            queue.append(nb)
    return False


def _infer_branch_links_from_columns(
    recalled_lower: set[str],
    anchors: set[str],
    column_map_by_lower: dict[str, dict[str, ColumnMetaRow]],
) -> dict[str, str]:
    """对未注册关系的召回表，从字段描述推断关联汇聚表。"""
    inferred: dict[str, str] = {}
    for table_lower in recalled_lower:
        cols = column_map_by_lower.get(table_lower) or {}
        for col in cols.values():
            desc = (col.description_manual or col.column_comment_auto or "").lower()
            if "关联" not in desc and "外键" not in desc:
                continue
            for anchor in anchors:
                if anchor.lower() in desc or _normalize_name(anchor) in desc:
                    inferred[table_lower] = anchor
                    break
            if table_lower in inferred:
                break
    return inferred


def _is_likely_source_table(table: str, meta: TableMetaRow | None, branch_links: dict[str, str]) -> bool:
    if table in branch_links:
        return True
    if meta is None:
        return False
    role = (meta.table_role or "").strip().lower()
    if role in _SOURCE_ROLES:
        return True
    if role in ("dimension", "lookup", "dict"):
        return False
    return bool(meta.biz_domain)


def _hub_tiebreaker(anchor: str, meta: TableMetaRow | None) -> int:
    score = 0
    if meta:
        role = (meta.table_role or "").lower()
        if role in ("dimension", "lookup", "dict"):
            score += 10
        if meta.biz_domain and "活动" in meta.biz_domain:
            score += 5
    if "activity" in anchor.lower():
        score += 3
    return score


def _resolve_branch_links(
    recalled_tables: list[str],
    relations: list[RelationRow],
    table_meta: dict[str, TableMetaRow],
    column_map: dict[str, dict[str, ColumnMetaRow]],
) -> dict[str, str]:
    """为每个来源表选定唯一汇聚表（多 n:1 时优先高分 hub）。"""
    recalled_lower = {_normalize_name(t) for t in recalled_tables if t}
    name_by_lower = {_normalize_name(t): t for t in recalled_tables if t}
    meta_by_lower = {_normalize_name(k): v for k, v in table_meta.items()}
    col_by_lower = {_normalize_name(k): v for k, v in column_map.items()}

    edges: list[tuple[str, str]] = []
    for rel in relations:
        if rel.status != 1 or not _is_n_to_one(rel.cardinality):
            continue
        if _normalize_name(rel.from_table_name) not in recalled_lower:
            continue
        edges.append((rel.from_table_name, rel.to_table_name))

    anchors_from_edges = {anchor for _, anchor in edges}
    inferred = _infer_branch_links_from_columns(recalled_lower, anchors_from_edges, col_by_lower)
    for src_lower, anchor in inferred.items():
        src = name_by_lower.get(src_lower, src_lower)
        edges.append((src, anchor))

    hub_sources: dict[str, set[str]] = defaultdict(set)
    for src, anchor in edges:
        hub_sources[anchor].add(src)

    src_anchor_options: dict[str, list[str]] = defaultdict(list)
    for src, anchor in edges:
        src_anchor_options[src].append(anchor)

    links: dict[str, str] = {}
    for src, anchors in src_anchor_options.items():
        best = max(
            anchors,
            key=lambda a: (
                len(hub_sources[a]),
                _hub_tiebreaker(a, meta_by_lower.get(_normalize_name(a))),
            ),
        )
        links[src] = best
    return links


def detect_multi_branch_aggregate(
    *,
    recalled_tables: list[str],
    relations: list[RelationRow],
    table_meta: dict[str, TableMetaRow] | None = None,
    column_map: dict[str, dict[str, ColumnMetaRow]] | None = None,
    metrics: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    若多个来源表仅经同一汇聚表关联且彼此无表关系路径，返回拆分建议。

    Returns:
        None 表示无需强制拆分；否则含 query_shape / aggregate_strategy / anchor_table 等。
    """
    if len(recalled_tables) < 2:
        return None

    recalled_lower = {_normalize_name(t) for t in recalled_tables if t}
    if len(recalled_lower) < 2:
        return None

    table_meta = table_meta or {}
    column_map = column_map or {}
    meta_by_lower = {_normalize_name(k): v for k, v in table_meta.items()}

    branch_links_named = _resolve_branch_links(
        recalled_tables,
        relations,
        table_meta,
        column_map,
    )

    if len(branch_links_named) < 2:
        return None

    adj = _build_adjacency(relations)

    by_anchor: dict[str, list[str]] = defaultdict(list)
    for src, anchor in branch_links_named.items():
        if not _is_likely_source_table(src, meta_by_lower.get(_normalize_name(src)), branch_links_named):
            continue
        by_anchor[anchor].append(src)

    metric_count = len(metrics or [])
    for anchor, sources in by_anchor.items():
        if len(sources) < 2:
            continue
        disconnected_pairs: list[tuple[str, str]] = []
        for i, s1 in enumerate(sources):
            for s2 in sources[i + 1 :]:
                if not _has_path_avoiding_anchor(s1, s2, adj, anchor):
                    disconnected_pairs.append((s1, s2))
        if not disconnected_pairs:
            continue
        if metric_count < 2 and len(sources) < 2:
            continue

        metric_groups: list[dict[str, Any]] = []
        for src in sources:
            meta = meta_by_lower.get(_normalize_name(src))
            metric_groups.append(
                {
                    "source_tables": [src],
                    "anchor_table": anchor,
                    "biz_domain": (meta.biz_domain if meta and meta.biz_domain else None),
                }
            )

        return {
            "query_shape": _QUERY_SHAPE_MULTI_BRANCH,
            "aggregate_strategy": _AGGREGATE_STRATEGY_SUBQUERY,
            "anchor_table": anchor,
            "branch_tables": sources,
            "metric_groups": metric_groups,
            "structure_reason": (
                f"来源表 {', '.join(sources)} 均关联汇聚表 {anchor}，"
                f"但彼此无表关系路径，禁止多路同时 JOIN 后 SUM；"
                f"应使用标量子查询分路聚合（MySQL 5.7）。"
            ),
        }
    return None


def apply_plan_structure_analysis(
    plan: dict[str, Any],
    analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    """将结构分析结果合并进 plan（Python 判定优先）。"""
    if not analysis:
        return plan

    plan = dict(plan)
    plan["query_shape"] = analysis["query_shape"]
    plan["aggregate_strategy"] = analysis["aggregate_strategy"]
    plan["anchor_table"] = analysis.get("anchor_table")
    plan["metric_groups"] = analysis.get("metric_groups") or []
    plan["structure_reason"] = analysis.get("structure_reason")

    if plan.get("complexity") == "low":
        plan["complexity"] = "high"

    # 子查询分路：单条 SQL，不走 multi_sql 分步执行
    plan["multi_sql"] = False

    sources = list(plan.get("sources") or [])
    tag = "heuristic:multi_branch_aggregate"
    if tag not in sources:
        sources.append(tag)
    plan["sources"] = sources

    steps = list(plan.get("steps") or [])
    if not steps:
        metrics = plan.get("metrics") or []
        steps = [
            {
                "id": 1,
                "goal": (
                    f"经汇聚表 {analysis.get('anchor_table')} 分路聚合："
                    + "、".join(metrics)
                    if metrics
                    else "分路聚合多业务域指标"
                ),
                "tables": [analysis.get("anchor_table")] + (analysis.get("branch_tables") or []),
                "needs_tool": ["list_relations", "describe_table"],
                "sql_step": False,
                "metrics": metrics,
            }
        ]
    else:
        steps = [dict(s) for s in steps]
        for step in steps:
            step["sql_step"] = False
            goal = step.get("goal") or ""
            if "分路" not in goal and "子查询" not in goal:
                step["goal"] = (
                    f"{goal}（{analysis.get('structure_reason', '分路聚合')}）"
                ).strip()

    plan["steps"] = steps
    return plan
