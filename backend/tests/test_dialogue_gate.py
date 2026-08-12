"""对话门禁：规则短路、AskUserQuestion 裁剪、路由（领域无关）。"""

from app.agent.ask_user_payload import (
    build_ask_user_from_slots,
    clarification_payload_dict,
    clip_ask_user_question,
)
from app.agent.dialogue_nodes import route_after_dialogue, route_after_merge_recall
from app.agent.dialogue_rules import detect_topic_switch, rule_route_dialogue
from app.agent.graph import build_ask_graph, clear_ask_graph_cache
from app.agent.plan_nodes import route_after_plan
from app.schemas.ask import AskResponse, ClarificationPayload


def test_rule_chitchat_greeting():
    r = rule_route_dialogue("你好")
    assert r is not None
    assert r["dialogue_act"] == "chitchat"
    assert "跳绳" not in (r.get("chat_reply") or "")


def test_rule_help():
    r = rule_route_dialogue("你能做什么")
    assert r is not None
    assert r["dialogue_act"] == "chitchat"
    assert "跳绳" not in (r.get("chat_reply") or "")


def test_rule_out_of_scope_poem():
    r = rule_route_dialogue("帮我写首诗")
    assert r is not None
    assert r["dialogue_act"] == "out_of_scope"


def test_rule_clarify_partial_entity():
    r = rule_route_dialogue("帮我看看华东区")
    assert r is not None
    assert r["dialogue_act"] == "clarify"
    assert "time_range" in r["missing_slots"] or "metric" in r["missing_slots"]
    assert r.get("filled_slots", {}).get("entity") == "华东区"


def test_rule_data_query_complete():
    r = rule_route_dialogue("本月销售额是多少")
    assert r is not None
    assert r["dialogue_act"] == "data_query"


def test_topic_switch_detect():
    pending = {
        "original_question": "帮我看看华东区",
        "filled_slots": {"entity": "华东区"},
        "missing_slots": ["time_range", "metric"],
    }
    assert detect_topic_switch("华南区订单数量近7天", pending) is True
    assert detect_topic_switch("近7天", pending) is False
    assert detect_topic_switch("近7天数量", pending) is False


def test_topic_switch_full_question_without_entity_slot():
    """pending 无 entity 时，完整新问句不得并入旧销售额澄清。"""
    pending = {
        "original_question": "今年1到12月和去年1到12月销售额每个月去对比",
        "filled_slots": {},
        "missing_slots": ["entity", "metric"],
    }
    assert (
        detect_topic_switch(
            "今年的学生人数对比去年的学生人数增长了多少？只查基础数据就行了",
            pending,
        )
        is True
    )
    assert detect_topic_switch("学生数据", pending) is False
    assert detect_topic_switch("近7天", pending) is False


def test_ask_clarification_empty_slots_does_not_invent_time_metric():
    """空 missing_slots 时不得默认出时间/指标题。"""
    from app.agent.ask_user_payload import build_ask_user_from_slots

    ask = build_ask_user_from_slots(
        missing_slots=[],
        filled_slots={"entity": "学生数据"},
        clarify_question="问句末尾与订单表无直连路径，请确认口径",
        max_questions=2,
        max_options=4,
    )
    ids = [q["id"] for q in ask["questions"]]
    assert "time_range" not in ids
    assert "metric" not in ids
    assert ids == ["general"]


def test_route_after_plan_soft_ambiguity_continues():
    """plan 仅有 ambiguities、无缺槽/无出题 → 不应进 ask_clarification。"""
    # soft path 在 plan_question 节点消化；路由侧 need_clarification 应为 False
    assert (
        route_after_plan(
            {
                "plan_skipped": False,
                "ready_to_execute": True,
                "need_clarification": False,
                "plan": {"ready_to_execute": True, "ambiguities": ["软歧义"]},
            }
        )
        == "agent_loop"
    )


def test_clip_ask_user_question_hard_limits():
    payload = {
        "title": "确认",
        "questions": [
            {
                "id": f"q{i}",
                "prompt": f"问题{i}",
                "options": [{"id": f"o{j}", "label": f"选项{j}"} for j in range(8)],
            }
            for i in range(6)
        ],
    }
    clipped = clip_ask_user_question(payload, max_questions=2, max_options=4)
    assert clipped is not None
    assert len(clipped["questions"]) == 2
    assert len(clipped["questions"][0]["options"]) == 4


def test_build_ask_user_from_slots():
    ask = build_ask_user_from_slots(
        missing_slots=["time_range", "metric"],
        filled_slots={"entity": "华东区"},
        max_questions=2,
        max_options=4,
    )
    assert ask["questions"]
    assert len(ask["questions"]) <= 2
    labels = [
        opt["label"]
        for q in ask["questions"]
        for opt in q.get("options") or []
    ]
    assert "参与人数" not in labels
    assert "本学期" not in labels


def test_clarification_payload_camel_serialization():
    ask = build_ask_user_from_slots(missing_slots=["time_range"], filled_slots={"entity": "华东区"})
    raw = clarification_payload_dict(
        ask_user=ask,
        missing_slots=["time_range"],
        thread_id="clr_test",
    )
    payload = ClarificationPayload.model_validate(raw)
    dumped = payload.model_dump(by_alias=True)
    assert "threadId" in dumped
    assert dumped["missingSlots"] == ["time_range"]
    assert dumped["questions"]


def test_ask_response_includes_clarification_status():
    resp = AskResponse(
        trace_id="t1",
        status="need_clarification",
        answer="请补充时间范围",
        dialogue_act="clarify",
        clarification=ClarificationPayload(question="想看哪个时间？", missing_slots=["time_range"]),
    )
    data = resp.model_dump(by_alias=True)
    assert data["status"] == "need_clarification"
    assert data["dialogueAct"] == "clarify"
    assert data["clarification"]["question"]


def test_route_after_dialogue():
    assert route_after_dialogue({"dialogue_act": "chitchat"}) == "reply_chat"
    assert route_after_dialogue({"dialogue_act": "out_of_scope"}) == "reply_chat"
    assert route_after_dialogue({"dialogue_act": "clarify"}) == "ask_clarification"
    assert route_after_dialogue({"dialogue_act": "data_query"}) == "process_memory_context"
    assert route_after_dialogue({"dialogue_gate_skipped": True, "dialogue_act": "chitchat"}) == (
        "process_memory_context"
    )


def test_route_after_plan_clarify():
    assert (
        route_after_plan(
            {
                "need_clarification": True,
                "dialogue_act": "clarify",
                "ready_to_execute": False,
            }
        )
        == "ask_clarification"
    )
    assert route_after_plan({"plan_skipped": True, "ready_to_execute": True}) == "generate_sql"
    assert route_after_plan({"plan_skipped": False, "ready_to_execute": True}) == "agent_loop"


def test_route_after_merge_recall():
    assert route_after_merge_recall({"need_clarification": True}) == "ask_clarification"
    assert route_after_merge_recall({"status": "out_of_scope"}) == "format_answer"
    assert route_after_merge_recall({}) == "do_recall_sql_examples"


def test_recall_gate_rule_flags_low_score():
    from app.agent.context_builder import MergedRecallContext
    from app.agent.recall_gate_llm import recall_gate_rule_flags
    from app.retrieval.hybrid import RecalledMetric, RecalledTable
    from config.settings import Settings

    settings = Settings(
        DIALOGUE_RECALL_TABLE_MIN=0.15,
        DIALOGUE_RECALL_METRIC_MIN=0.12,
    )
    merged = MergedRecallContext(
        keywords=[],
        recall_mode="hybrid",
        recalled_tables=[
            RecalledTable(
                table_id=1,
                table_name="sport_order",
                search_text="订单",
                score=0.03,
                recall_mode="hybrid",
            )
        ],
        metrics=[
            RecalledMetric(
                metric_id=1,
                metric_code="qzs_month_participants",
                metric_name="本校本月活动参与人数",
                search_text="活动",
                score=0.03,
                recall_mode="hybrid",
            )
        ],
    )
    flags = recall_gate_rule_flags(merged, settings, "今年销售额同比")
    assert flags["should_adjudicate"] is True
    assert flags["low_table"] is True


def test_recall_gate_normalize_proceed():
    from app.agent.recall_gate_llm import _normalize_adjudication
    from config.settings import Settings

    settings = Settings()
    out = _normalize_adjudication(
        {
            "decision": "proceed",
            "reason": "有 sport_order.order_total 可支撑销售额",
        },
        question="销售额",
        flags={"low_table": True, "low_metric": True},
        settings=settings,
    )
    assert out["decision"] == "proceed"


def test_recall_gate_normalize_clarify_builds_ask_user():
    from app.agent.recall_gate_llm import _normalize_adjudication
    from config.settings import Settings

    settings = Settings()
    out = _normalize_adjudication(
        {
            "decision": "clarify",
            "reason": "金额口径不清",
            "clarify_question": "看订单总额还是商品件数？",
            "clarify_options": ["订单总额", "商品件数"],
            "missing_slots": ["metric"],
        },
        question="本月销售怎么样",
        flags={"low_metric": True, "low_table": False},
        settings=settings,
    )
    assert out["decision"] == "clarify"
    assert out["ask_user_question"] is not None
    assert out["ask_user_question"]["questions"]


def test_recall_gate_rule_fallback_skips_noise_metrics_when_low_table():
    from app.agent.context_builder import MergedRecallContext
    from app.agent.recall_gate_llm import build_rule_fallback_clarify
    from app.retrieval.hybrid import RecalledMetric, RecalledTable
    from config.settings import Settings

    settings = Settings()
    merged = MergedRecallContext(
        keywords=[],
        recall_mode="hybrid",
        recalled_tables=[
            RecalledTable(
                table_id=1,
                table_name="sport_order",
                search_text="订单",
                score=0.03,
                recall_mode="hybrid",
            )
        ],
        metrics=[
            RecalledMetric(
                metric_id=1,
                metric_code="qzs_month_participants",
                metric_name="本校本月活动参与人数",
                search_text="活动",
                score=0.03,
                recall_mode="hybrid",
            )
        ],
    )
    flags = {
        "low_table": True,
        "low_metric": True,
        "empty_recall": False,
    }
    fb = build_rule_fallback_clarify(merged, flags, settings)
    assert fb["decision"] == "clarify"
    # 低表分时不把噪声指标塞进推荐 options
    labels = []
    for q in (fb["ask_user_question"] or {}).get("questions") or []:
        for opt in q.get("options") or []:
            labels.append(opt.get("label"))
    assert "本校本月活动参与人数" not in labels


def test_graph_includes_dialogue_nodes():
    clear_ask_graph_cache()
    graph = build_ask_graph()
    nodes = graph.get_graph().nodes
    for name in ("route_dialogue", "reply_chat", "ask_clarification"):
        assert name in nodes
