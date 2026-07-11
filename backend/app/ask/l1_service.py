"""
L1 样例：可见性过滤、候选拼装与 Prompt 格式化。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.context import UserContext, UserRole
from app.meta.repository import SqlExampleRow


@dataclass(frozen=True)
class L1ExampleCandidate:
    """知识库召回或 LLM 精选后的 L1 样例。"""

    id: int
    question_pattern: str
    sql_text: str
    description: str | None
    recall_score: float = 0.0
    select_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question_pattern": self.question_pattern,
            "description": self.description,
            "sql_text": self.sql_text,
            "recall_score": self.recall_score,
            "select_reason": self.select_reason,
        }


def _parse_meta(meta_json: str | None) -> dict:
    if not meta_json:
        return {}
    try:
        data = json.loads(meta_json)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def is_l1_visible(row: SqlExampleRow, ctx: UserContext) -> bool:
    """草稿、未发布、角色不符的样例不参与召回与精选。"""
    meta = _parse_meta(row.meta_json)
    if meta.get("draft"):
        return False
    if row.review_status == 0:
        return False
    if row.role_scope and ctx.role.value != row.role_scope:
        return False
    if bool(meta.get("adminOnly", False)) and ctx.role == UserRole.SCHOOL:
        return False
    return True


def is_indexable_l1_row(row) -> bool:
    """索引构建时跳过草稿样例。"""
    meta = _parse_meta(getattr(row, "meta_json", None))
    return not meta.get("draft")


def row_to_candidate(row: SqlExampleRow, *, recall_score: float = 0.0) -> L1ExampleCandidate:
    return L1ExampleCandidate(
        id=row.id,
        question_pattern=row.question_pattern,
        sql_text=row.sql_text,
        description=row.description,
        recall_score=recall_score,
    )


def candidates_from_rows(
    rows: list[SqlExampleRow],
    *,
    scores: dict[int, float] | None = None,
) -> list[L1ExampleCandidate]:
    out: list[L1ExampleCandidate] = []
    score_map = scores or {}
    for row in rows:
        out.append(row_to_candidate(row, recall_score=score_map.get(row.id, 0.0)))
    return out


def format_l1_prompt_lines(
    selected: list[L1ExampleCandidate],
    *,
    sql_max_chars: int = 500,
) -> list[str]:
    """将精选 L1 样例格式化为 Prompt 段落。"""
    if not selected:
        return []
    lines = ["【相似样例 SQL（仅供参考；表/列以当前白名单与候选字段为准，勿照搬）】"]
    for ex in selected:
        lines.append(f"问法示例：{ex.question_pattern}")
        if ex.description:
            lines.append(f"说明：{ex.description[:300]}")
        if ex.select_reason:
            lines.append(f"选用理由：{ex.select_reason[:200]}")
        lines.append(f"SQL：{ex.sql_text[:sql_max_chars]}")
        lines.append("")
    return lines


def append_l1_to_context(context_text: str, selected: list[L1ExampleCandidate]) -> str:
    """在基础 context 后追加 L1 段落。"""
    lines = format_l1_prompt_lines(selected)
    if not lines:
        return context_text
    base = (context_text or "").rstrip()
    block = "\n".join(lines).strip()
    return f"{base}\n\n{block}" if base else block


def primary_l1_sql(selected: list[L1ExampleCandidate]) -> str | None:
    """plan 分步补全用的主参考 SQL（取第一条）。"""
    if not selected:
        return None
    return selected[0].sql_text
