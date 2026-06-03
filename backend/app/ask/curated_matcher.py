"""
L1 样例匹配：从 copilot_sql_example 读取规则与 SQL（动态配置，无需改代码发版）。
"""

from __future__ import annotations

import re

from app.ask.models import MatchedQuery
from app.ask.semantic_repository import CuratedSqlExample
from app.core.context import UserContext, UserRole


def _project_clause(question: str) -> str:
    """问句含跳绳/跑步时追加 project_id 过滤（1=跳绳，20=跑步）。"""
    if "跳绳" in question:
        return " AND project_id = 1"
    if "跑步" in question:
        return " AND project_id = 20"
    return ""


def _matches_question(question: str, meta: dict) -> bool:
    """按 meta_json 中的 matchAll / matchAny / matchAllGroups 判断。"""
    for kw in meta.get("matchAll", []):
        if kw not in question:
            return False
    any_list = meta.get("matchAny", [])
    if any_list and not any(k in question for k in any_list):
        return False
    for group in meta.get("matchAllGroups", []):
        if not isinstance(group, list) or not any(k in question for k in group):
            return False
    # 未配置任何规则时，用 question_pattern 作子串参考（宽松）
    if not meta.get("matchAll") and not meta.get("matchAny") and not meta.get("matchAllGroups"):
        pattern = meta.get("questionPattern") or ""
        if pattern and pattern not in question and question not in pattern:
            return False
    return True


def _apply_school_filter(sql: str, ctx: UserContext, meta: dict, admin_only: bool) -> str:
    """学校账户自动追加 sch_id 条件（与 MVP 行为一致）。"""
    if admin_only or ctx.role != UserRole.SCHOOL:
        return sql
    if not meta.get("requiresSchoolFilter", True):
        return sql
    if "sch_id" in sql.lower():
        return sql
    return f"{sql} AND sch_id = :sch_id"


def _extract_tables(sql: str, meta: dict) -> tuple[str, ...]:
    if tables := meta.get("tables"):
        if isinstance(tables, list):
            return tuple(t.lower() for t in tables if t)
    found = re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)", sql, flags=re.IGNORECASE)
    return tuple(dict.fromkeys(t.lower() for t in found))


def match_curated(
    question: str,
    ctx: UserContext,
    examples: list[CuratedSqlExample],
) -> MatchedQuery | None:
    """
    在已加载的样例列表中匹配问句。

    按 degrade_priority 顺序尝试，返回首个命中项。
    """
    q = question.strip()
    if not q or not examples:
        return None

    project_clause = ""
    for ex in examples:
        meta = ex.meta
        if not _matches_question(q, meta):
            continue

        admin_only = bool(meta.get("adminOnly", False))
        if admin_only and ctx.role == UserRole.SCHOOL:
            continue
        if ex.role_scope and ctx.role.value != ex.role_scope:
            continue

        if meta.get("appendProjectClause", True) and not project_clause:
            project_clause = _project_clause(q)

        sql = ex.sql_text
        if project_clause and project_clause.strip() not in sql:
            sql = f"{sql}{project_clause}"
        sql = _apply_school_filter(sql, ctx, meta, admin_only)

        params: dict = {}
        if ctx.role == UserRole.SCHOOL and ":sch_id" in sql.lower():
            if ctx.active_sch_id is not None:
                params["sch_id"] = ctx.active_sch_id

        return MatchedQuery(
            sql=sql,
            params=params,
            tables=_extract_tables(sql, meta),
            value_column=str(meta.get("valueColumn", "cnt")),
            answer_template=str(
                meta.get("answerTemplate", "查询完成，共 {row_count} 条记录。")
            ),
            admin_only=admin_only,
            degrade_level=1,
            match_source="curated",
        )

    return None
