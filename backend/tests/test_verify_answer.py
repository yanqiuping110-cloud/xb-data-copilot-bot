"""verify_answer 与统一召回单元测试（第 9～11 周）。"""

from app.agent.context_builder import MergedRecallContext
from app.agent.plan_nodes import _inject_code_sources
from app.agent.verify_nodes import route_after_verify, verify_answer_heuristic
from app.retrieval.hybrid import RecalledCodeArtifact, RecalledTable
from app.retrieval.unified import boost_tables_by_code_artifacts


def test_verify_empty_result_fails():
    result = verify_answer_heuristic("本校各年级参与人数", ["cnt"], [])
    assert result["passed"] is False
    assert result["reason"] == "empty_result"


def test_verify_heuristic_passes_simple():
    result = verify_answer_heuristic(
        "总数",
        ["cnt"],
        [[100]],
    )
    assert result["passed"] is True


def test_route_after_verify_failed_goes_correct_sql():
    from app.agent.state import AskGraphState

    state: AskGraphState = {
        "verify_passed": False,
        "correct_sql_count": 0,
    }
    assert route_after_verify(state) == "correct_sql"


def test_route_after_verify_passed_goes_build_chart():
    from app.agent.state import AskGraphState

    state: AskGraphState = {"verify_passed": True}
    assert route_after_verify(state) == "build_chart"


def test_boost_tables_by_code_artifacts():
    tables = [
        RecalledTable(
            table_id=1,
            table_name="sport_activity_qzs_record",
            search_text="活动",
            score=0.8,
            recall_mode="hybrid",
        )
    ]
    artifacts = [
        RecalledCodeArtifact(
            artifact_id=1,
            repo_id=1,
            title="报表",
            artifact_type="controller_method",
            search_text="活动报表",
            score=0.9,
            recall_mode="hybrid",
            tables=["sport_activity_qzs_record"],
        )
    ]
    boosted = boost_tables_by_code_artifacts(tables, artifacts)
    assert boosted[0].score > tables[0].score


def test_inject_code_sources_into_plan():
    merged = MergedRecallContext(
        keywords=["活动"],
        recall_mode="hybrid",
        code_artifacts=[
            RecalledCodeArtifact(
                artifact_id=42,
                repo_id=1,
                title="活动报表",
                artifact_type="controller_method",
                search_text="活动参与",
                score=0.9,
                recall_mode="hybrid",
                tables=["sport_activity_qzs_record"],
            )
        ],
    )
    plan = {
        "complexity": "high",
        "intent": "multi_dim_report",
        "steps": [{"id": 1, "goal": "确认表", "needs_tool": ["describe_table"]}],
        "sources": ["meta:recall"],
    }
    out = _inject_code_sources(plan, merged)
    assert "code:artifact:42" in out["sources"]
    assert "search_code_artifacts" in out["steps"][-1]["needs_tool"]
