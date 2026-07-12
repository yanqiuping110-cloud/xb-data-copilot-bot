"""Plan 结构分析单测。"""

from app.agent.plan_analyzer import (
    apply_plan_structure_analysis,
    detect_multi_branch_aggregate,
)
from app.meta.repository import ColumnMetaRow, RelationRow, TableMetaRow


def _rel(
    from_table: str,
    to_table: str,
    *,
    cardinality: str = "n:1",
) -> RelationRow:
    return RelationRow(
        id=1,
        from_table_id=1,
        from_table_name=from_table,
        from_column="x_id",
        to_table_id=2,
        to_table_name=to_table,
        to_column="id",
        relation_type="logical_join",
        join_hint=None,
        cardinality=cardinality,
        status=1,
    )


def _table(name: str, *, role: str = "fact", domain: str = "测试") -> TableMetaRow:
    return TableMetaRow(
        id=1,
        table_name=name,
        table_role=role,
        biz_domain=domain,
        table_comment_auto=None,
        description_manual=None,
        grain=None,
        sch_id_column="sch_id",
        last_introspected_at=None,
        status=1,
    )


def _col(table_id: int, name: str, desc: str) -> ColumnMetaRow:
    return ColumnMetaRow(
        id=1,
        table_id=table_id,
        column_name=name,
        ordinal_position=1,
        data_type="int",
        column_comment_auto=None,
        description_manual=desc,
        column_role=None,
        alias_json=None,
        is_nullable=1,
        status=1,
        recall_enabled=1,
    )


def test_detect_multi_branch_activity_compare():
    relations = [
        _rel("sport_activity_qzs_time", "sport_activity_new"),
        _rel("sport_activity_qzs_time", "base_student"),
    ]
    table_meta = {
        "sport_activity_qzs_time": _table("sport_activity_qzs_time", domain="活动打卡"),
        "sport_order": _table("sport_order", domain="订单"),
        "sport_activity_new": _table("sport_activity_new", role="dimension", domain="活动"),
    }
    column_map = {
        "sport_order": {
            "use_type_id": _col(
                2,
                "use_type_id",
                "关联sport_activity_new表的id字段，用于判定订单属于哪个活动",
            )
        }
    }
    analysis = detect_multi_branch_aggregate(
        recalled_tables=[
            "sport_activity_new",
            "sport_activity_qzs_time",
            "sport_order",
        ],
        relations=relations,
        table_meta=table_meta,
        column_map=column_map,
        metrics=["活动人数", "活动打卡次数", "订单金额"],
    )
    assert analysis is not None
    assert analysis["query_shape"] == "multi_branch_aggregate"
    assert analysis["aggregate_strategy"] == "subquery_per_branch"
    assert analysis["anchor_table"] == "sport_activity_new"
    assert "sport_activity_qzs_time" in analysis["branch_tables"]
    assert "sport_order" in analysis["branch_tables"]


def test_detect_hub_spoke_still_splits_with_order_relation():
    """注册 sport_order→活动表后，经汇聚表连通仍应拆分。"""
    relations = [
        _rel("sport_activity_qzs_time", "sport_activity_new"),
        _rel("sport_order", "sport_activity_new"),
    ]
    table_meta = {
        "sport_activity_qzs_time": _table("sport_activity_qzs_time", domain="活动打卡"),
        "sport_order": _table("sport_order", domain="订单"),
    }
    analysis = detect_multi_branch_aggregate(
        recalled_tables=["sport_activity_new", "sport_activity_qzs_time", "sport_order"],
        relations=relations,
        table_meta=table_meta,
        metrics=["活动人数", "订单金额"],
    )
    assert analysis is not None
    assert analysis["aggregate_strategy"] == "subquery_per_branch"


def test_detect_skips_when_sources_connected_directly():
    relations = [
        _rel("sport_activity_qzs_time", "sport_activity_new"),
        _rel("sport_activity_qzs_time", "sport_order"),
    ]
    table_meta = {
        "sport_activity_qzs_time": _table("sport_activity_qzs_time"),
        "sport_order": _table("sport_order"),
    }
    analysis = detect_multi_branch_aggregate(
        recalled_tables=["sport_activity_qzs_time", "sport_order"],
        relations=relations,
        table_meta=table_meta,
        metrics=["打卡", "订单"],
    )
    assert analysis is None


def test_apply_plan_structure_sets_strategy():
    plan = {
        "complexity": "high",
        "intent": "entity_compare",
        "multi_sql": False,
        "metrics": ["活动人数", "订单金额"],
        "steps": [{"id": 1, "goal": "对比两个活动", "sql_step": False, "needs_tool": []}],
    }
    analysis = {
        "query_shape": "multi_branch_aggregate",
        "aggregate_strategy": "subquery_per_branch",
        "anchor_table": "sport_activity_new",
        "branch_tables": ["sport_activity_qzs_time", "sport_order"],
        "metric_groups": [],
        "structure_reason": "test",
    }
    out = apply_plan_structure_analysis(plan, analysis)
    assert out["aggregate_strategy"] == "subquery_per_branch"
    assert out["multi_sql"] is False
    assert out["complexity"] == "high"
    assert "heuristic:multi_branch_aggregate" in out["sources"]
