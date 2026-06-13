"""MyBatis XML <select> 规则解析器（§11.8.2 · 第 10 周）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# SQL 中表名粗提取（FROM/JOIN 后）
_TABLE_FROM_RE = re.compile(
    r"(?:FROM|JOIN)\s+[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)
_SELECT_BLOCK_RE = re.compile(
    r"<select\s+[^>]*id\s*=\s*[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</select>",
    re.IGNORECASE,
)
_SELECT_ID_RE = re.compile(r"id\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


@dataclass
class ParsedMapperSelect:
    """解析出的 MyBatis select 语句块。"""

    statement_id: str
    qualified_name: str
    file_path: str
    sql_text: str
    tables: list[str]
    raw_snippet: str


@dataclass
class MapperParseResult:
    """单 Mapper XML 解析结果。"""

    namespace: str
    file_path: str
    selects: list[ParsedMapperSelect] = field(default_factory=list)


_NAMESPACE_RE = re.compile(r"<mapper\s+[^>]*namespace\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


def extract_tables_from_sql(sql_text: str) -> list[str]:
    """从 SQL 文本 regex 提取表名（去重保序）。"""
    seen: set[str] = set()
    tables: list[str] = []
    for m in _TABLE_FROM_RE.finditer(sql_text):
        name = m.group(1)
        if name.lower() in ("select", "where", "on", "and", "left", "right", "inner"):
            continue
        if name not in seen:
            seen.add(name)
            tables.append(name)
    return tables


def parse_mapper_xml(content: str, file_path: str) -> MapperParseResult | None:
    """解析 Mapper XML 中所有 <select> 块及涉及表名。"""
    ns_match = _NAMESPACE_RE.search(content)
    namespace = ns_match.group(1) if ns_match else file_path
    selects: list[ParsedMapperSelect] = []

    for block in _SELECT_BLOCK_RE.finditer(content):
        stmt_id = block.group(1)
        inner = block.group(2)
        sql_text = re.sub(r"<[^>]+>", " ", inner)
        sql_text = re.sub(r"\s+", " ", sql_text).strip()
        tables = extract_tables_from_sql(sql_text)
        qualified = f"{namespace}.{stmt_id}"
        snippet = block.group(0)[:8000]
        selects.append(
            ParsedMapperSelect(
                statement_id=stmt_id,
                qualified_name=qualified,
                file_path=file_path,
                sql_text=sql_text,
                tables=tables,
                raw_snippet=snippet,
            )
        )

    if not selects:
        return None
    return MapperParseResult(namespace=namespace, file_path=file_path, selects=selects)
