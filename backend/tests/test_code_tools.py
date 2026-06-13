"""代码 Agent 工具注册单测（第 12 周）。"""

from app.agent.tools.executor import TOOL_REGISTRY


def test_tool_registry_has_code_tools():
    expected = {
        "search_code_artifacts",
        "get_code_artifact",
        "trace_code_flow",
        "link_artifact_to_meta",
    }
    assert expected.issubset(set(TOOL_REGISTRY.keys()))
