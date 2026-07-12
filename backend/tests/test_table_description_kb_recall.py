"""表级 description_manual 与知识库直出召回单测。"""

import json

from app.agent.context_builder import apply_kb_recall_limits, merge_retrieved_info
from app.meta.table_description import (
    parse_table_description_manual,
    table_default_where,
    table_effective_description,
)
from app.meta.repository import TableMetaRow
from app.retrieval.hybrid import HybridRecallResult, RecalledTable
from config.settings import Settings


def _settings(**overrides) -> Settings:
    base = {
        "JWT_SECRET": "test-secret-min-32-chars-long-enough",
        "RECALL_TOP_K_TABLE": 8,
        "RECALL_TOP_K_COLUMN": 5,
        "RECALL_TOP_K_METRIC": 5,
        "RECALL_TOP_K_VALUE": 5,
    }
    base.update(overrides)
    return Settings(**base)


def _table_row(**kwargs) -> TableMetaRow:
    defaults = {
        "id": 1,
        "table_name": "sport_order",
        "table_role": "fact",
        "biz_domain": "order",
        "table_comment_auto": None,
        "description_manual": None,
        "grain": None,
        "sch_id_column": "sch_id",
        "last_introspected_at": None,
        "status": 1,
    }
    defaults.update(kwargs)
    return TableMetaRow(**defaults)


def test_parse_table_description_manual_json():
    raw = json.dumps(
        {
            "description": "订单表",
            "default_where": "is_delete = 0 AND pay_status = 1",
        },
        ensure_ascii=False,
    )
    desc, where = parse_table_description_manual(raw)
    assert desc == "订单表"
    assert where == "is_delete = 0 AND pay_status = 1"


def test_parse_table_description_manual_plain_text():
    desc, where = parse_table_description_manual("订单表，默认 is_delete=0")
    assert desc == "订单表，默认 is_delete=0"
    assert where is None


def test_table_helpers_from_structured_manual():
    row = _table_row(
        description_manual=json.dumps(
            {"description": "订单事实表", "default_where": "pay_status = 1"},
            ensure_ascii=False,
        )
    )
    assert table_effective_description(row) == "订单事实表"
    assert table_default_where(row) == "pay_status = 1"


def test_apply_kb_recall_limits_keeps_top_tables(monkeypatch):
    monkeypatch.setattr(
        "app.agent.context_builder.get_allowed_tables",
        lambda: frozenset({"sport_order", "base_student", "sport_activity_new"}),
    )
    recall = HybridRecallResult(
        keywords=["订单"],
        tables=[
            RecalledTable(1, "sport_order", "订单", 0.9, "vector_hybrid"),
            RecalledTable(2, "base_student", "学生", 0.5, "vector_hybrid"),
            RecalledTable(3, "sport_activity_new", "活动", 0.3, "vector_hybrid"),
            RecalledTable(4, "noise_table", "噪声", 0.95, "vector_hybrid"),
        ],
    )
    merged = merge_retrieved_info(recall)
    merged = apply_kb_recall_limits(merged, _settings())
    assert merged.table_names == ["sport_order", "base_student", "sport_activity_new"]
    assert "noise_table" not in merged.table_names
