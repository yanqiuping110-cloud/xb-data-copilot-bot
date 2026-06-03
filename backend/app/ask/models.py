"""
问数匹配结果模型（硬编码 MVP 与 copilot_sql_example L1 共用）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MatchedQuery:
    """匹配到的预置查询。"""

    sql: str
    tables: tuple[str, ...]
    value_column: str
    answer_template: str
    params: dict = field(default_factory=dict)
    admin_only: bool = False
    degrade_level: int = 0  # 0=硬编码兜底，1=库内样例命中（L1）
    match_source: str = "mvp"  # mvp | curated
