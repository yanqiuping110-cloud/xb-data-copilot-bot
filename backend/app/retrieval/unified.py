"""
统一召回：meta 四路 + code artifact 一路并行加权（§11.8.3 · 第 11 周）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.hybrid import (
    HybridRecallResult,
    HybridRetriever,
    RecalledCodeArtifact,
    RecalledTable,
)
from config.settings import Settings


@dataclass
class UnifiedRecallResult:
    """meta + code 合并召回结果。"""

    hybrid: HybridRecallResult
    code_artifacts: list[RecalledCodeArtifact] = field(default_factory=list)
    code_recall_mode: str = "disabled"
    table_boost_applied: bool = False


def boost_tables_by_code_artifacts(
    tables: list[RecalledTable],
    artifacts: list[RecalledCodeArtifact],
    *,
    boost: float = 0.15,
) -> list[RecalledTable]:
    """
    artifact.tables_json 命中表名时提升对应 RecalledTable 得分。
    """
    if not tables or not artifacts:
        return tables
    artifact_tables: set[str] = set()
    for art in artifacts:
        artifact_tables.update(art.tables)
    if not artifact_tables:
        return tables

    boosted: list[RecalledTable] = []
    for t in tables:
        extra = boost if t.table_name in artifact_tables else 0.0
        boosted.append(
            RecalledTable(
                table_id=t.table_id,
                table_name=t.table_name,
                search_text=t.search_text,
                score=t.score + extra,
                recall_mode=t.recall_mode,
            )
        )
    boosted.sort(key=lambda x: x.score, reverse=True)
    return boosted


class UnifiedRetriever:
    """并行 meta HybridRetriever + code artifact 召回。"""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._hybrid = HybridRetriever(session, settings)

    async def close(self) -> None:
        await self._hybrid.close()

    async def recall_all(
        self,
        question: str,
        keywords: list[str] | None = None,
    ) -> UnifiedRecallResult:
        """执行 meta 四路 + code 一路召回，并对表得分加权。"""
        hybrid = await self._hybrid.recall_all(question, keywords)
        code_items: list[RecalledCodeArtifact] = []
        code_mode = "disabled"
        if self._settings.code_knowledge_enabled:
            code_items, code_mode = await self._hybrid.recall_code_artifacts(question, keywords)

        boosted = boost_tables_by_code_artifacts(hybrid.tables, code_items)
        applied = boosted != hybrid.tables
        hybrid.tables = boosted
        hybrid.code_artifacts = code_items
        return UnifiedRecallResult(
            hybrid=hybrid,
            code_artifacts=code_items,
            code_recall_mode=code_mode,
            table_boost_applied=applied,
        )
