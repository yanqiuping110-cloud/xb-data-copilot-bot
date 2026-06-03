"""
MVP 问句 → 硬编码 SQL 匹配（库内样例未命中时的兜底）。

数据源：sport_activity_qzs_record（亲子活动打卡）。
"""

from __future__ import annotations

from app.ask.models import MatchedQuery
from app.core.context import UserContext, UserRole
from app.sql.whitelist import fallback_allowed_tables

_QZS_TABLE = next(iter(fallback_allowed_tables()))


def _project_clause(question: str) -> str:
    if "跳绳" in question:
        return " AND project_id = 1"
    if "跑步" in question:
        return " AND project_id = 20"
    return ""


def match_question(question: str, ctx: UserContext) -> MatchedQuery | None:
    """根据问句关键词匹配硬编码 SQL。"""
    q = question.strip()
    if not q:
        return None

    project_clause = _project_clause(q)

    if any(k in q for k in ("全平台", "平台汇总", "平台活动")):
        if ctx.role == UserRole.SCHOOL:
            return None
        return MatchedQuery(
            sql=(
                f"SELECT COUNT(*) AS cnt "
                f"FROM {_QZS_TABLE} "
                f"WHERE DATE(create_time) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)"
                f"{project_clause}"
            ),
            tables=(_QZS_TABLE,),
            value_column="cnt",
            answer_template="昨日全平台活动打卡人次为 {cnt} 次。",
            admin_only=True,
        )

    if ("参与" in q or "参与人数" in q) and ("本月" in q or "这个月" in q):
        return _school_month_participants(ctx, project_clause)

    if ("7" in q or "七" in q or "最近" in q) and ("趋势" in q or "每日" in q or "每天" in q):
        return _school_weekly_trend(ctx, project_clause)

    if "参与人数" in q or ("参与" in q and "人数" in q):
        return _school_month_participants(ctx, project_clause)

    return None


def _school_month_participants(ctx: UserContext, project_clause: str) -> MatchedQuery:
    params: dict = {}
    sch_clause = ""
    if ctx.role == UserRole.SCHOOL:
        sch_clause = " AND sch_id = :sch_id"
        if ctx.active_sch_id is not None:
            params["sch_id"] = ctx.active_sch_id

    return MatchedQuery(
        sql=(
            f"SELECT COUNT(DISTINCT people_id) AS cnt "
            f"FROM {_QZS_TABLE} "
            f"WHERE create_time >= DATE_FORMAT(CURDATE(), '%Y-%m-01')"
            f"{sch_clause}{project_clause}"
        ),
        params=params,
        tables=(_QZS_TABLE,),
        value_column="cnt",
        answer_template="本校本月活动参与人数为 {cnt} 人。",
    )


def _school_weekly_trend(ctx: UserContext, project_clause: str) -> MatchedQuery:
    params: dict = {}
    sch_clause = ""
    if ctx.role == UserRole.SCHOOL:
        sch_clause = " AND sch_id = :sch_id"
        if ctx.active_sch_id is not None:
            params["sch_id"] = ctx.active_sch_id

    return MatchedQuery(
        sql=(
            f"SELECT DATE(create_time) AS stat_day, COUNT(DISTINCT people_id) AS cnt "
            f"FROM {_QZS_TABLE} "
            f"WHERE create_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
            f"{sch_clause}{project_clause} "
            f"GROUP BY DATE(create_time) ORDER BY stat_day"
        ),
        params=params,
        tables=(_QZS_TABLE,),
        value_column="cnt",
        answer_template="已返回最近 7 天每日参与人数，共 {row_count} 天数据。",
    )
