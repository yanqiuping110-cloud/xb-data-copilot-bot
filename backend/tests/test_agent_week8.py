"""Agent Loop、分步 SQL、probe 与路由单元测试（第 8 周）。"""

import pytest

from app.agent.agent_llm import _fallback_action
from app.agent.agent_nodes import route_after_agent_loop
from app.agent.plan_nodes import route_after_plan
from app.agent.state import AskGraphState
from app.agent.tools.executor import TOOL_REGISTRY
from app.core.context import UserContext, UserRole
from app.sql.guard import SqlGuardError, validate_probe_sql
from config.settings import Settings


def _settings() -> Settings:
    return Settings(JWT_SECRET="test-secret", AGENT_MAX_CORRECT=2)


def _ctx(role: UserRole = UserRole.ADMIN) -> UserContext:
    return UserContext(
        trace_id="t",
        user_id=1,
        username="u",
        role=role,
        active_sch_id=None,
        bound_sch_ids=[],
    )


def test_tool_registry_has_run_probe_sql():
    assert "run_probe_sql" in TOOL_REGISTRY


def test_route_after_plan_skipped_goes_to_generate_sql():
    state: AskGraphState = {"plan_skipped": True}
    assert route_after_plan(state) == "generate_sql"


def test_route_after_plan_complex_goes_to_agent_loop():
    state: AskGraphState = {"plan_skipped": False, "plan": {"complexity": "high", "steps": [{}, {}]}}
    assert route_after_plan(state) == "agent_loop"


def test_route_after_agent_loop_continues_when_not_done():
    state: AskGraphState = {"agent_loop_done": False}
    assert route_after_agent_loop(state) == "agent_loop"


def test_route_after_agent_loop_builds_context_when_done():
    state: AskGraphState = {"agent_loop_done": True}
    assert route_after_agent_loop(state) == "build_agent_context"


def test_fallback_action_runs_plan_tools_in_order():
    plan = {
        "steps": [
            {"needs_tool": ["describe_table", "list_relations"]},
            {"needs_tool": ["get_join_path"]},
        ]
    }
    first = _fallback_action(plan, [], default_tables=["t_a", "t_b"], question="对比")
    assert first["action"] == "tool"
    assert first["tool"] == "describe_table"

    second = _fallback_action(
        plan,
        [{"tool": "describe_table", "result": {}}],
        default_tables=["t_a", "t_b"],
        question="对比",
    )
    assert second["tool"] == "list_relations"

    done = _fallback_action(
        plan,
        [
            {"tool": "describe_table", "result": {}},
            {"tool": "list_relations", "result": {}},
            {"tool": "get_join_path", "result": {}},
        ],
        default_tables=["t_a", "t_b"],
        question="对比",
    )
    assert done["action"] == "finish"


def test_describe_table_visits_each_plan_table_once_then_finish():
    from app.agent.agent_llm import _fallback_action, _needs_tools_complete, _next_describe_table

    plan = {
        "anchor_table": "sport_activity_new",
        "metric_groups": [
            {"source_tables": ["sport_activity_qzs_time"], "anchor_table": "sport_activity_new"},
            {"source_tables": ["sport_order"], "anchor_table": "sport_activity_new"},
        ],
        "steps": [{"needs_tool": ["describe_table"]}],
    }
    tables = ["sport_activity_qzs_time", "sport_activity_new", "sport_order", "base_school"]
    obs: list[dict] = []
    seen: list[str] = []
    for _ in range(5):
        if _needs_tools_complete(plan, obs, default_tables=tables):
            break
        action = _fallback_action(plan, obs, default_tables=tables, question="按月统计")
        assert action["action"] == "tool"
        assert action["tool"] == "describe_table"
        table = action["args"]["table"]
        assert table not in seen
        seen.append(table)
        obs.append(
            {
                "tool": "describe_table",
                "args": {"table": table},
                "result": {"table": table, "column_count": 10},
            }
        )
    assert seen == ["sport_activity_new", "sport_activity_qzs_time", "sport_order"]
    assert _needs_tools_complete(plan, obs, default_tables=tables)
    assert _next_describe_table(tables, obs, plan=plan) == ""
    assert _fallback_action(plan, obs, default_tables=tables, question="按月统计")["action"] == "finish"


def test_needs_tools_complete_blocks_extra_tools():
    from app.agent.agent_llm import _needs_tools_complete

    plan = {"steps": [{"needs_tool": ["describe_table"]}]}
    tables = ["sport_activity_qzs_time"]
    obs = [
        {
            "tool": "describe_table",
            "args": {"table": "sport_activity_qzs_time"},
            "result": {"table": "sport_activity_qzs_time", "column_count": 3},
        }
    ]
    assert _needs_tools_complete(plan, obs, default_tables=tables) is True


def test_tool_call_fingerprint_dedup_same_table_and_join_pair():
    from app.agent.agent_llm import (
        is_duplicate_tool_call,
        tool_call_fingerprint,
        _avoid_duplicate_action,
        _fallback_action,
    )

    assert tool_call_fingerprint("describe_table", {"table": "Orders"}) == tool_call_fingerprint(
        "describe_table", {"table": "orders"}
    )
    assert tool_call_fingerprint(
        "get_join_path", {"from_table": "a", "to_table": "b"}
    ) == tool_call_fingerprint("get_join_path", {"from_table": "b", "to_table": "a"})

    obs = [
        {
            "tool": "list_relations",
            "args": {"table": "orders"},
            "result": {"count": 2},
        },
        {
            "tool": "search_metrics",
            "args": {"query": "销售额"},
            "result": {"count": 1},
        },
    ]
    assert is_duplicate_tool_call("list_relations", {"table": "Orders"}, obs)
    assert is_duplicate_tool_call("search_metrics", {"query": "  销售额  "}, obs)
    assert not is_duplicate_tool_call("list_relations", {"table": "users"}, obs)

    dup = {"action": "tool", "tool": "list_relations", "args": {"table": "orders"}}
    plan = {"steps": [{"needs_tool": ["list_relations", "describe_table"]}]}
    fb = _fallback_action(plan, obs, default_tables=["orders", "users"], question="q")
    out = _avoid_duplicate_action(dup, observations=obs, fallback=fb)
    assert out["action"] == "tool"
    assert out["tool"] == "describe_table"
    assert out["args"]["table"] in ("orders", "users")

    only_dup_obs = [
        {
            "tool": "describe_table",
            "args": {"table": "orders"},
            "result": {"column_count": 1},
        }
    ]
    plan2 = {"steps": [{"needs_tool": ["describe_table"]}]}
    fb2 = _fallback_action(plan2, only_dup_obs, default_tables=["orders"], question="q")
    out2 = _avoid_duplicate_action(
        {"action": "tool", "tool": "describe_table", "args": {"table": "orders"}},
        observations=only_dup_obs,
        fallback=fb2,
    )
    assert out2["action"] == "finish"


def test_format_observations_includes_ban_list():
    from app.agent.agent_llm import _format_observations

    text = _format_observations(
        [
            {
                "tool": "describe_table",
                "args": {"table": "orders"},
                "result": {"column_count": 5},
            }
        ]
    )
    assert "describe_table(table=orders)" in text
    assert "禁止重复调用" in text
    assert "describe_table|orders" in text


def test_validate_probe_sql_caps_limit():
    sql = validate_probe_sql(
        "SELECT COUNT(*) AS cnt FROM sport_activity_qzs_record",
        _ctx(),
        max_rows=10,
        settings=_settings(),
    )
    assert "LIMIT" in sql.upper()


def test_validate_probe_sql_rejects_insert():
    with pytest.raises(SqlGuardError) as exc:
        validate_probe_sql("DELETE FROM t", _ctx(), settings=_settings())
    assert exc.value.code == "BUSINESS_DML_FORBIDDEN"


def test_route_after_execute_success_goes_verify():
    from app.agent.nodes import route_after_execute

    state: AskGraphState = {"status": "running"}
    assert route_after_execute(state) == "verify_answer"


def test_route_correct_sql_twice_then_format():
    from app.agent.nodes import route_after_execute, route_after_validate

    state: AskGraphState = {"error_code": "PARSE_ERROR", "correct_sql_count": 0}
    assert route_after_validate(state) == "correct_sql"

    state = {"error_code": "PARSE_ERROR", "correct_sql_count": 1}
    assert route_after_validate(state) == "correct_sql"

    state = {"error_code": "PARSE_ERROR", "correct_sql_count": 2}
    assert route_after_validate(state) == "correct_sql"

    state = {"error_code": "PARSE_ERROR", "correct_sql_count": 3}
    assert route_after_validate(state) == "format_answer"

    state = {"error_code": "SQL_EXEC_ERROR", "correct_sql_count": 1}
    assert route_after_execute(state) == "correct_sql"

    state = {"error_code": "SQL_EXEC_ERROR", "correct_sql_count": 3}
    assert route_after_execute(state) == "verify_answer"
