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
    assert route_after_merge_recall({}) == "do_recall_sql_examples"


def test_graph_includes_dialogue_nodes():
    clear_ask_graph_cache()
    graph = build_ask_graph()
    nodes = graph.get_graph().nodes
    for name in ("route_dialogue", "reply_chat", "ask_clarification"):
        assert name in nodes
