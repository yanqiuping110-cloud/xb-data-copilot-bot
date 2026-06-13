"""LangGraph 编译与节点命名单测。"""

from app.agent.graph import build_ask_graph, clear_ask_graph_cache


def test_build_ask_graph_compiles_without_state_key_conflict():
    clear_ask_graph_cache()
    graph = build_ask_graph()
    assert graph is not None


def test_graph_includes_plan_question_node():
    clear_ask_graph_cache()
    graph = build_ask_graph()
    nodes = graph.get_graph().nodes
    assert "plan_question" in nodes


def test_graph_includes_week8_agent_nodes():
    clear_ask_graph_cache()
    graph = build_ask_graph()
    nodes = graph.get_graph().nodes
    for name in ("agent_loop", "build_agent_context", "generate_sql_step", "verify_answer"):
        assert name in nodes
