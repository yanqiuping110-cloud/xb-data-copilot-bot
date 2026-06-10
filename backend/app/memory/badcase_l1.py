"""
Badcase → L1 样例草稿：从问句与 SQL 生成 meta_json（运营审核后发布）。
"""

from __future__ import annotations

import json
import re

_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)", flags=re.IGNORECASE)

# 问句中常见统计词，用于生成宽松 matchAll
_STAT_TERMS = ("参与", "参与人数", "人次", "打卡", "趋势", "汇总", "人数", "个数")


def extract_tables_from_sql(sql: str) -> list[str]:
    """从 SQL 提取 FROM/JOIN 表名（去重保序）。"""
    if not sql:
        return []
    return list(dict.fromkeys(t.lower() for t in _TABLE_RE.findall(sql)))


def _guess_match_keywords(question: str) -> dict:
    """根据问句生成 L1 匹配规则草案。"""
    q = (question or "").strip()
    meta: dict = {}
    found = [t for t in _STAT_TERMS if t in q]
    if found:
        meta["matchAll"] = found[:3]
    if "本月" in q or "这个月" in q:
        meta.setdefault("matchAllGroups", []).append(["本月", "这个月"])
    if "上周" in q or "最近" in q:
        meta.setdefault("matchAny", []).extend(["上周", "最近7天", "最近"])
    if "全平台" in q or "平台" in q:
        meta["adminOnly"] = True
        meta["requiresSchoolFilter"] = False
        meta.setdefault("matchAny", []).append("全平台")
    if "跳绳" in q:
        meta.setdefault("matchAny", []).append("跳绳")
    if "跑步" in q:
        meta.setdefault("matchAny", []).append("跑步")
    if not meta.get("matchAll") and not meta.get("matchAny") and not meta.get("matchAllGroups"):
        # 无规则时用问句前 30 字作 questionPattern 参考
        meta["questionPattern"] = q[:80]
    return meta


def build_l1_draft_from_badcase(
    *,
    question: str,
    sql_text: str,
    role: str | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    构建 L1 样例草稿字段（未入库）。

    draft=true 的样例不参与软参考注入 Prompt，运营调低 degrade_priority 并去掉 draft 后发布。
    """
    sql = (sql_text or "").strip()
    if not sql:
        raise ValueError("SQL 不能为空")

    tables = extract_tables_from_sql(sql)
    meta = _guess_match_keywords(question)
    meta.update(
        {
            "draft": True,
            "sourceTraceId": trace_id,
            "answerTemplate": "查询完成，共 {row_count} 条记录。",
            "valueColumn": "cnt",
            "tables": tables,
        }
    )
    return {
        "question_pattern": (question or "").strip()[:512] or "（来自 badcase）",
        "sql_text": sql,
        "meta_json": json.dumps(meta, ensure_ascii=False),
        "role_scope": role,
        "degrade_priority": 999,
    }
