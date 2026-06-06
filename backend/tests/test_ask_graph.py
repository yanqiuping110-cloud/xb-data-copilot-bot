"""LangGraph 编译与节点命名单测。"""

from app.agent.graph import build_ask_graph, clear_ask_graph_cache


def test_build_ask_graph_compiles_without_state_key_conflict():
    clear_ask_graph_cache()
    graph = build_ask_graph()
    assert graph is not None
