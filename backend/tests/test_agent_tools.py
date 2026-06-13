"""Agent MySQL 工具与 plan_question 单元测试（第 7 周）。"""

from app.agent.plan_nodes import (
    _fallback_plan,
    assess_complexity_heuristic,
    route_after_plan,
)
from app.agent.context_builder import MergedRecallContext
from app.agent.state import AskGraphState
from app.agent.tools.executor import TOOL_REGISTRY, tool_span_name
from app.agent.tools.meta_tools import _build_relation_adjacency, _neighbor_table
from app.meta.repository import RelationRow


def _rel(
    from_t: str,
    to_t: str,
    *,
    from_col: str = "id",
    to_col: str = "fk_id",
) -> RelationRow:
    return RelationRow(
        id=1,
        from_table_id=1,
        from_table_name=from_t,
        from_column=from_col,
        to_table_id=2,
        to_table_name=to_t,
        to_column=to_col,
        relation_type="logical_join",
        join_hint=None,
        cardinality=None,
        status=1,
    )


def test_tool_registry_has_week7_tools():
    expected = {
        "describe_table",
        "list_relations",
        "get_join_path",
        "search_metrics",
        "search_field_values",
        "search_sql_examples",
        "run_probe_sql",
        "search_code_artifacts",
        "get_code_artifact",
        "trace_code_flow",
        "link_artifact_to_meta",
    }
    assert expected.issubset(set(TOOL_REGISTRY.keys()))


def test_tool_span_name():
    assert tool_span_name("describe_table") == "tool_describe_table"


def test_assess_complexity_high_for_multi_table():
    merged = MergedRecallContext(
        keywords=["对比"],
        recall_mode="hybrid",
        table_names=["sport_activity_qzs_record", "sport_project"],
    )
    assert assess_complexity_heuristic("对比本月跳绳与跑步参与人数", merged) == "high"


def test_assess_complexity_low_for_simple():
    merged = MergedRecallContext(
        keywords=["跳绳"],
        recall_mode="hybrid",
        table_names=["sport_activity_qzs_record"],
    )
    assert assess_complexity_heuristic("本校本月跳绳参与人数", merged) == "low"


def test_fallback_plan_complex_has_at_least_two_steps():
    merged = MergedRecallContext(
        keywords=["对比"],
        recall_mode="hybrid",
        table_names=["sport_activity_qzs_record", "sport_project"],
    )
    plan = _fallback_plan("对比本月跳绳与跑步参与人数", merged)
    assert plan["complexity"] == "high"
    assert len(plan["steps"]) >= 2


def test_route_after_plan_goes_to_generate_sql_when_skipped():
    state: AskGraphState = {"plan_skipped": True}
    assert route_after_plan(state) == "generate_sql"


def test_route_after_plan_goes_to_agent_loop_when_complex():
    state: AskGraphState = {"plan_skipped": False}
    assert route_after_plan(state) == "agent_loop"


def test_route_after_plan_error_goes_to_format():
    state: AskGraphState = {"error_code": "NO_SQL"}
    assert route_after_plan(state) == "format_answer"


def test_join_path_adjacency_neighbor():
    rel = _rel("table_a", "table_b")
    assert _neighbor_table(rel, "table_a") == "table_b"
    assert _neighbor_table(rel, "table_b") == "table_a"


def test_build_relation_adjacency_undirected():
    rels = [_rel("a", "b"), _rel("b", "c")]
    adj = _build_relation_adjacency(rels)
    assert "a" in adj and "b" in adj and "c" in adj
    assert len(adj["b"]) == 2
