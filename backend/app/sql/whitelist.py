"""
业务库表白名单：优先 copilot_metric_definition.relevant_tables，无配置时用代码默认值。

问数仅允许查询白名单内表；学校维度字段名统一为 sch_id。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.semantic_repository import SemanticRepository
from app.meta.repository import MetaRepository

# 无 DB 配置时的兜底（与种子指标一致）
_FALLBACK_TABLES: frozenset[str] = frozenset(
    {
        "sport_activity_qzs_record",
    }
)

SCH_ID_COLUMN = "sch_id"

# 进程内缓存，由 /ask 在匹配前刷新
_cached_allowed: frozenset[str] | None = None


def fallback_allowed_tables() -> frozenset[str]:
    """代码内默认表白名单（种子未执行或指标表为空时使用）。"""
    return _FALLBACK_TABLES


def get_allowed_tables() -> frozenset[str]:
    """当前生效的业务表白名单。"""
    if _cached_allowed is not None:
        return _cached_allowed
    return _FALLBACK_TABLES


async def refresh_allowed_tables(session: AsyncSession) -> frozenset[str]:
    """从 copilot 库加载并刷新缓存；优先 table_meta，其次指标表，最后兜底。"""
    global _cached_allowed
    meta_repo = MetaRepository(session)
    from_meta = await meta_repo.load_allowed_table_names()
    if from_meta:
        _cached_allowed = frozenset(from_meta)
        return _cached_allowed
    repo = SemanticRepository(session)
    from_db = await repo.load_allowed_table_names()
    _cached_allowed = frozenset(from_db) if from_db else _FALLBACK_TABLES
    return _cached_allowed


# 兼容旧 import：测试与脚本仍可引用 ALLOWED_TABLES
ALLOWED_TABLES = get_allowed_tables()
