"""
问数聊天对话框对前端的响应裁剪。

仅用于 /ask 与 /sessions/.../messages 等聊天 UI 接口；
元数据管理、badcase 运营后台等其它 API 不受此模块影响。
"""

from __future__ import annotations

from app.core.context import UserContext, UserRole


def can_show_sql_in_chat(ctx: UserContext) -> bool:
    """聊天对话框内是否可向当前用户展示 SQL（仅系统管理员）。"""
    return ctx.role == UserRole.ADMIN


def sanitize_chat_sql(ctx: UserContext, sql: str | None) -> str | None:
    """聊天 UI 响应中的 SQL 字段；非 ADMIN 一律不下发。"""
    if not sql or not can_show_sql_in_chat(ctx):
        return None
    return sql
