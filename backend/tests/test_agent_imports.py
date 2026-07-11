"""Agent 模块 import 冒烟测试，防止运行时 NameError（函数未 import）。"""

from __future__ import annotations

import importlib
import inspect


def _module_public_callables(module_name: str) -> list[str]:
    mod = importlib.import_module(module_name)
    names: list[str] = []
    for name, obj in vars(mod).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(obj) or inspect.iscoroutinefunction(obj):
            names.append(name)
    return names


def test_plan_llm_complete_messages_resolves():
    import app.agent.plan_llm as plan_llm

    assert hasattr(plan_llm, "complete_messages")
    from app.agent.llm_client import complete_messages

    assert plan_llm.complete_messages is complete_messages


def test_plan_nodes_generate_plan_resolves():
    import app.agent.plan_nodes as plan_nodes

    assert hasattr(plan_nodes, "generate_plan_from_llm")
    from app.agent.plan_llm import generate_plan_from_llm

    assert plan_nodes.generate_plan_from_llm is generate_plan_from_llm


def test_chart_pipeline_modules_import():
    modules = [
        "app.agent.chart_builder",
        "app.agent.chart_nodes",
        "app.agent.plan_llm",
        "app.agent.plan_nodes",
        "app.agent.graph",
        "app.schemas.chart",
    ]
    for name in modules:
        mod = importlib.import_module(name)
        assert mod is not None


def test_build_chart_node_callable():
    from app.agent.chart_nodes import build_chart

    assert inspect.iscoroutinefunction(build_chart)


def test_retrieval_modules_import():
    importlib.import_module("app.retrieval.zvec_client")
    importlib.import_module("app.retrieval.search_index")
    from app.retrieval.search_index import create_search_index_client
    from config.settings import get_settings

    client = create_search_index_client(get_settings())
    assert client is not None


def test_infer_visualization_from_question_chart_intent():
    from app.agent.chart_builder import infer_visualization_from_question

    intent = infer_visualization_from_question("用图表展示2026年每个月的活动打卡人数")
    assert intent["enabled"] is True
    assert intent.get("user_explicit") is True
    assert "line" in intent.get("preferred_types", []) or "bar" in intent.get("preferred_types", [])
