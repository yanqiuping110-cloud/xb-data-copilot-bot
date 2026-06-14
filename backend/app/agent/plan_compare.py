"""
分步 SQL plan 工具函数（无问句关键词硬编码）。
"""

from __future__ import annotations

import re
from typing import Any


def short_entity_label(entity: str, *, max_len: int = 24) -> str:
    """列名前缀用的短标签。"""
    text = re.sub(r"\s+", "", entity)
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def extract_activity_ids_from_sql(sql: str) -> list[int]:
    """从 SQL 文本提取 activity_id / id IN (...) 候选。"""
    ids: list[int] = []
    for raw in re.findall(r"activity_id\s*=\s*(\d+)", sql, flags=re.IGNORECASE):
        n = int(raw)
        if n not in ids:
            ids.append(n)
    in_match = re.search(
        r"(?:activity_id|[aA]\d*\.id)\s+IN\s*\(([^)]+)\)",
        sql,
        flags=re.IGNORECASE,
    )
    if in_match:
        for part in in_match.group(1).split(","):
            part = part.strip()
            if part.isdigit():
                n = int(part)
                if n not in ids:
                    ids.append(n)
    return ids[:4]


def enrich_sql_steps_from_reference_sql(plan: dict[str, Any], sql: str | None) -> dict[str, Any]:
    """当 plan 已声明 multi_sql 且步骤缺 activity_id 时，从参考 SQL 按序补全 filter_hint。"""
    if not sql or not plan.get("multi_sql"):
        return plan
    sql_steps = get_sql_execution_steps(plan)
    if len(sql_steps) < 2:
        return plan
    ids = extract_activity_ids_from_sql(sql)
    if len(ids) < 2:
        return plan
    for i, step in enumerate(sql_steps):
        if i < len(ids):
            hint = dict(step.get("filter_hint") or {})
            if hint.get("activity_id") is None:
                hint["activity_id"] = ids[i]
            step["filter_hint"] = hint
    return plan


def plan_requires_multi_sql(plan: dict[str, Any] | None) -> bool:
    """plan 是否要求分步 SQL（由 LLM multi_sql 或 sql_step 步数推断）。"""
    if not plan:
        return False
    if plan.get("multi_sql"):
        return True
    return len(get_sql_execution_steps(plan)) >= 2


def get_sql_execution_steps(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """从 plan 中取出需要独立执行 SQL 的步骤。"""
    if not plan:
        return []
    steps = plan.get("steps") or []
    return [s for s in steps if s.get("sql_step")]
