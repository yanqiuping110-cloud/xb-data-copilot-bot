"""
代码 artifact 检索文本拼装（§11.8 · 第 11 周）。
"""

from __future__ import annotations

from app.code.models import IndexableCodeArtifactRow


def build_code_search_text(
    *,
    title: str,
    summary_text: str | None,
    tables: list[str],
    artifact_type: str,
) -> str:
    """拼接 title + 摘要 + 表名 + 类型，供 MySQL search_text 与 ES 索引。"""
    parts = [title, artifact_type]
    if summary_text:
        parts.append(summary_text.strip())
    if tables:
        parts.append("表: " + ", ".join(tables))
    return " | ".join(p for p in parts if p)


def build_indexable_search_text(row: IndexableCodeArtifactRow) -> str:
    """从 IndexableCodeArtifactRow 再生成 ES 文档 search_text。"""
    import json

    tables: list[str] = []
    if row.tables_json:
        try:
            tables = json.loads(row.tables_json)
        except json.JSONDecodeError:
            tables = []
    return build_code_search_text(
        title=row.title,
        summary_text=row.summary_text,
        tables=tables if isinstance(tables, list) else [],
        artifact_type=row.artifact_type,
    )
