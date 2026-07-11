"""Research Graph 单测。"""

from app.research.graph import get_research_graph


def test_research_graph_compiles():
    graph = get_research_graph()
    assert graph is not None


def test_research_graph_normalize_node():
    graph = get_research_graph()
    result = graph.invoke({"request_text": "  测试分析  ", "section_index": 0})
    assert result.get("request_text") == "测试分析"
