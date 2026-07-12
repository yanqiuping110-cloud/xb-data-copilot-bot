"""
混合召回索引文本拼装（使用 effective 描述 + 别名）。
"""

from __future__ import annotations

from app.meta.effective import effective_description
from app.meta.table_description import parse_table_description_manual
from app.meta.repository import (
    IndexableColumnRow,
    IndexableFieldValueRow,
    IndexableMetricRow,
    IndexableTableRow,
    parse_alias_json,
)


def build_table_search_text(row: IndexableTableRow) -> str:
    """表级向量索引文本：表名 + 有效描述 + default_where + 域/角色/粒度 + 字段摘要。"""
    parts = [row.table_name]
    desc, default_where = parse_table_description_manual(row.description_manual)
    if not desc:
        desc = effective_description(row.description_manual, row.table_comment_auto)
    if desc:
        parts.append(desc)
    if default_where:
        parts.append(f"默认条件 {default_where}")
    if row.biz_domain:
        parts.append(row.biz_domain)
    if row.table_role:
        parts.append(row.table_role)
    if row.grain:
        parts.append(row.grain)
    if row.column_summary:
        parts.append(row.column_summary)
    return " ".join(parts).strip()


def build_column_search_text(row: IndexableColumnRow) -> str:
    """字段向量索引文本：表.列 + 有效描述 + 别名。"""
    parts = [f"{row.table_name}.{row.column_name}"]
    desc = effective_description(row.description_manual, row.column_comment_auto)
    if desc:
        parts.append(desc)
    aliases = parse_alias_json(row.alias_json)
    if aliases:
        parts.append(" ".join(aliases))
    if row.column_role:
        parts.append(row.column_role)
    return " ".join(parts).strip()


def build_metric_search_text(row: IndexableMetricRow) -> str:
    """指标向量索引文本：名称 + 描述 + 公式 + 别名。"""
    parts = [row.metric_name, row.metric_code]
    if row.description:
        parts.append(row.description)
    if row.formula_text:
        parts.append(row.formula_text)
    if row.relevant_tables:
        parts.append(row.relevant_tables)
    aliases = parse_alias_json(row.alias_json)
    if aliases:
        parts.append(" ".join(aliases))
    return " ".join(parts).strip()


def build_field_value_search_text(row: IndexableFieldValueRow) -> str:
    """字段取值全文索引文本：表.列=值 + 展示名 + 别名。"""
    parts = [f"{row.table_name}.{row.column_name}={row.value_text}"]
    if row.display_label:
        parts.append(row.display_label)
    aliases = parse_alias_json(row.alias_json)
    if aliases:
        parts.append(" ".join(aliases))
    return " ".join(parts).strip()


def build_sql_example_search_text(row) -> str:
    """L1 样例向量索引文本：问句模式 + 详细描述（不含 SQL 正文）。"""
    parts = [row.question_pattern]
    if getattr(row, "description", None):
        parts.append(str(row.description).strip())
    return " ".join(p for p in parts if p).strip()
