"""
copilot 库语义配置：样例 SQL、指标表（动态白名单来源）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class MetricDefinition:
    """copilot_metric_definition 一行，供 retrieve_context 使用。"""

    metric_code: str
    metric_name: str
    description: str | None
    relevant_tables: str | None
    alias_json: str | None


@dataclass(frozen=True)
class CuratedSqlExample:
    """copilot_sql_example 一行，供 L1 匹配。"""

    id: int
    question_pattern: str
    sql_text: str
    role_scope: str | None
    degrade_priority: int
    meta: dict
    review_status: int = 1


class SemanticRepository:
    """指标与样例 SQL 只读访问。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_metrics(self) -> list[MetricDefinition]:
        """启用且未删除的指标定义。"""
        result = await self._session.execute(
            text(
                """
                SELECT metric_code, metric_name, description, relevant_tables, alias_json
                FROM copilot_metric_definition
                WHERE status = 1 AND deleted = 0
                ORDER BY metric_code
                """
            )
        )
        return [
            MetricDefinition(
                metric_code=str(r["metric_code"]),
                metric_name=str(r["metric_name"]),
                description=r.get("description"),
                relevant_tables=r.get("relevant_tables"),
                alias_json=r.get("alias_json"),
            )
            for r in result.mappings().all()
        ]

    async def list_sql_examples(self) -> list[CuratedSqlExample]:
        """启用且未删除的样例，按 degrade_priority 升序。"""
        result = await self._session.execute(
            text(
                """
                SELECT id, question_pattern, sql_text, role_scope, degrade_priority, meta_json,
                       review_status
                FROM copilot_sql_example
                WHERE deleted = 0 AND COALESCE(review_status, 1) = 1
                ORDER BY degrade_priority ASC, id ASC
                """
            )
        )
        rows: list[CuratedSqlExample] = []
        for row in result.mappings().all():
            meta = _parse_meta(row.get("meta_json"))
            rows.append(
                CuratedSqlExample(
                    id=int(row["id"]),
                    question_pattern=str(row["question_pattern"]),
                    sql_text=str(row["sql_text"]).strip(),
                    role_scope=row.get("role_scope"),
                    degrade_priority=int(row["degrade_priority"]),
                    meta=meta,
                    review_status=int(row.get("review_status") or 1),
                )
            )
        return rows

    async def load_allowed_table_names(self) -> set[str]:
        """
        从 copilot_metric_definition.relevant_tables 汇总业务表白名单。

        无配置时返回空集，由调用方回退到代码内默认表。
        """
        result = await self._session.execute(
            text(
                """
                SELECT relevant_tables
                FROM copilot_metric_definition
                WHERE status = 1 AND deleted = 0 AND relevant_tables IS NOT NULL
                """
            )
        )
        tables: set[str] = set()
        for row in result.mappings().all():
            raw = row.get("relevant_tables")
            if not raw:
                continue
            for part in str(raw).split(","):
                name = part.strip().lower()
                if name:
                    tables.add(name)
        return tables


def _parse_meta(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
