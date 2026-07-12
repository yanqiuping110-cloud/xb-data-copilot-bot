"""
表级 description_manual 解析。

支持纯文本（向后兼容）或 JSON 结构化配置：

```json
{
  "description": "订单表，用于计算订单金额",
  "default_where": "is_delete = 0 AND pay_status = 1"
}
```
"""

from __future__ import annotations

import json
from typing import Any

from app.meta.effective import effective_description
from app.meta.repository import TableMetaRow


def parse_table_description_manual(raw: str | None) -> tuple[str | None, str | None]:
    """
    解析表级人工描述。

    Returns:
        (description_text, default_where)
    """
    if raw is None or not str(raw).strip():
        return None, None
    text = str(raw).strip()
    if not text.startswith("{"):
        return text, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    if not isinstance(data, dict):
        return text, None
    desc = _pick_str(data, "description", "desc")
    default_where = _pick_str(data, "default_where", "defaultWhere")
    if desc or default_where:
        return desc, default_where
    return text, None


def _pick_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def table_effective_description(table: TableMetaRow) -> str | None:
    """表有效描述：结构化 JSON 取 description，否则走 effective 合并。"""
    desc, _ = parse_table_description_manual(table.description_manual)
    if desc:
        return desc
    return effective_description(table.description_manual, table.table_comment_auto)


def table_default_where(table: TableMetaRow) -> str | None:
    """表级结构化 default_where。"""
    _, where = parse_table_description_manual(table.description_manual)
    return where
