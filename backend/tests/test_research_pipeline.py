"""Research pipeline 映射单测。"""

from app.research.pipeline import is_tool_node, pipeline_step_for_node


def test_pipeline_step_for_generate_sql():
    assert pipeline_step_for_node("generate_sql") == 4


def test_pipeline_step_for_format_answer():
    assert pipeline_step_for_node("format_answer") == 6


def test_tool_node_detection():
    assert is_tool_node("tool_run_probe_sql")
    assert not is_tool_node("execute_sql")
