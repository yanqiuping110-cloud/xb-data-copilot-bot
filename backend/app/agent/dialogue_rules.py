"""
对话门禁规则短路（零 LLM）。领域无关：不写死具体业务实体。
"""

from __future__ import annotations

import re
from typing import Any

_CHAT_GREETING = re.compile(
    r"^(你好|您好|在吗|嗨|哈喽|hello|hi|hey|早上好|中午好|晚上好)[!！.。~～]?$",
    re.IGNORECASE,
)
_HELP = re.compile(r"(你是谁|你能做什么|怎么用|如何使用|你会什么|帮助|help)", re.IGNORECASE)
_CANCEL = re.compile(r"^(取消|算了|不问了|不问这个了|换个问题|重新问)$")
_OUT_OF_SCOPE = re.compile(
    r"(写首诗|写一首诗|讲个笑话|翻译成|写代码|帮我编程|今天天气|炒股|谈恋爱|做晚饭|食谱)",
)
_TIME = re.compile(
    r"(近\d+天|最近\d+天|本周|本月|本年|今年|今日|今天|昨日|昨天|上周|上月|"
    r"\d{4}[-/年]\d{1,2}|累计|总共|一共|全年)"
)
_METRIC = re.compile(
    r"(人数|人次|数量|次数|金额|销售额|销量|销售|营收|收入|订单|占比|比率|率|趋势|排名|对比|"
    r"统计|汇总|合计|总量|均值|平均|同比|环比)"
)
_CUMULATIVE = re.compile(r"(累计|总共|一共|合计|全部历史)")
_TIME_METRIC_STRIP = re.compile(
    r"(近\d+天|最近\d+天|本周|本月|本年|今年|今日|今天|昨日|昨天|上周|上月|"
    r"\d{4}[-/年]\d{1,2}|累计|总共|一共|全年|"
    r"人数|人次|数量|次数|金额|销售额|销量|销售|营收|收入|订单|占比|比率|率|趋势|排名|对比|"
    r"统计|汇总|合计|总量|均值|平均|同比|环比|"
    r"帮我|看看|查一下|看下|了解下|说说|是多少|多少|的|了|呢|吗|啊|吧)"
)

# 通用示例问句（不绑定具体行业）
_EXAMPLE_FULL = "本月销售额是多少"
_EXAMPLE_TREND = "最近7天订单趋势"


def _content_residue(text: str) -> str:
    """去掉时间/指标/语气词后的内容残差，用于换题检测。"""
    t = _TIME_METRIC_STRIP.sub("", text or "")
    t = re.sub(r"[\s，。！？、,.!?;；：:]+", "", t)
    return t.strip()


def rule_route_dialogue(
    question: str,
    *,
    pending: dict[str, Any] | None = None,
    require_time_slot: bool = True,
) -> dict[str, Any] | None:
    """
    高确定性规则短路。

    Returns:
        路由结果 dict；无法判定时返回 None（交 LLM）。
    """
    q = (question or "").strip()
    if not q:
        return {
            "dialogue_act": "clarify",
            "confidence": 1.0,
            "resolved_question": q,
            "missing_slots": ["metric", "time_range"],
            "filled_slots": {},
            "clarify_question": (
                f"请用自然语言描述你想查询的数据，例如「{_EXAMPLE_FULL}」。"
            ),
            "clarify_options": [_EXAMPLE_FULL, _EXAMPLE_TREND],
            "reason": "空问句",
            "source": "rule",
        }

    if _CANCEL.match(q):
        return {
            "dialogue_act": "chitchat",
            "confidence": 1.0,
            "resolved_question": q,
            "missing_slots": [],
            "filled_slots": {},
            "clarify_question": None,
            "clarify_options": [],
            "reason": "用户取消",
            "cancel_pending": True,
            "chat_reply": "好的，已取消当前澄清。你可以直接提出新的问数问题。",
            "source": "rule",
        }

    if _CHAT_GREETING.match(q):
        return {
            "dialogue_act": "chitchat",
            "confidence": 0.99,
            "resolved_question": q,
            "missing_slots": [],
            "filled_slots": {},
            "chat_reply": (
                "你好！我是智能问数助手，可以基于业务元数据帮你查询数据。"
                f"例如：「{_EXAMPLE_FULL}」「{_EXAMPLE_TREND}」。"
            ),
            "reason": "寒暄",
            "source": "rule",
        }

    if _HELP.search(q) and len(q) <= 20:
        return {
            "dialogue_act": "chitchat",
            "confidence": 0.95,
            "resolved_question": q,
            "missing_slots": [],
            "filled_slots": {},
            "chat_reply": (
                "我可以基于已配置的业务元数据回答数据问题。"
                "请尽量写清「对象/维度 + 时间 + 指标」，"
                f"例如「{_EXAMPLE_FULL}」。"
            ),
            "reason": "能力说明",
            "source": "rule",
        }

    if _OUT_OF_SCOPE.search(q) and not _METRIC.search(q):
        return {
            "dialogue_act": "out_of_scope",
            "confidence": 0.9,
            "resolved_question": q,
            "missing_slots": [],
            "filled_slots": {},
            "chat_reply": (
                "这个问题不在问数范围内。我只能帮你查询已接入的业务数据，"
                "请换一个与数据统计相关的问题试试。"
            ),
            "reason": "域外",
            "source": "rule",
        }

    # 有 pending 时不在规则层做完整分流（由节点合并逻辑处理）
    if pending:
        return None

    # 极短无业务词
    if len(q) <= 2 and not _METRIC.search(q) and not _TIME.search(q):
        return {
            "dialogue_act": "clarify",
            "confidence": 0.85,
            "resolved_question": q,
            "missing_slots": ["metric", "time_range", "entity"],
            "filled_slots": {},
            "clarify_question": "能再具体一点吗？例如想看哪个对象、什么时间范围、哪个指标。",
            "clarify_options": ["近7天数量", "本月趋势"],
            "reason": "极短问句",
            "source": "rule",
        }

    has_time = bool(_TIME.search(q))
    has_metric = bool(_METRIC.search(q))
    has_cumulative = bool(_CUMULATIVE.search(q))

    # 「帮我看看X」类半截问：有对象但缺时间+指标
    look_pattern = re.match(r"^(帮我)?(看看|查一下|看下|了解下|说说)(.+)$", q)
    if look_pattern and not has_metric:
        entity = look_pattern.group(3).strip(" ，。！?？")
        missing = ["metric"]
        if require_time_slot and not has_time and not has_cumulative:
            missing.append("time_range")
        return {
            "dialogue_act": "clarify",
            "confidence": 0.88,
            "resolved_question": q,
            "missing_slots": missing,
            "filled_slots": {"entity": entity} if entity else {},
            "clarify_question": f"关于「{entity}」，你想看哪个指标？时间范围呢？"
            if entity
            else "请补充指标与时间范围。",
            "clarify_options": ["近7天数量", "本月趋势", "本年汇总"],
            "reason": "半截问缺指标/时间",
            "source": "rule",
        }

    # 「最近怎么样」类模糊
    if re.search(r"(最近怎么样|怎么样了|情况如何|整体如何)", q) and not has_metric:
        return {
            "dialogue_act": "clarify",
            "confidence": 0.9,
            "resolved_question": q,
            "missing_slots": ["metric", "entity", "time_range"],
            "filled_slots": {},
            "clarify_question": "你想了解哪方面的数据？请说明对象/指标与时间范围。",
            "clarify_options": [_EXAMPLE_FULL, _EXAMPLE_TREND],
            "reason": "模糊问句",
            "source": "rule",
        }

    # 有指标无时间：强制澄清时间（领域无关）
    if require_time_slot and not has_time and not has_cumulative and has_metric and len(q) < 40:
        return {
            "dialogue_act": "clarify",
            "confidence": 0.7,
            "resolved_question": q,
            "missing_slots": ["time_range"],
            "filled_slots": {},
            "clarify_question": "请补充时间范围，例如近7天、本月或本年。",
            "clarify_options": ["近7天", "本月", "本年"],
            "reason": "有指标无时间",
            "source": "rule",
        }

    # 完整感：有时间+指标 → 放行
    if has_time and has_metric:
        return {
            "dialogue_act": "data_query",
            "confidence": 0.8,
            "resolved_question": q,
            "missing_slots": [],
            "filled_slots": {},
            "reason": "规则判定可执行",
            "source": "rule",
        }

    return None


def _residues_diverged(a: str, b: str) -> bool:
    """两段内容残差是否明显不同（换题信号，不做行业词表）。"""
    if not a or not b:
        return False
    if a == b:
        return False
    if a in b or b in a:
        return False
    # 极短残差不判分叉，避免噪声
    return len(a) >= 2 and len(b) >= 2


def detect_topic_switch(question: str, pending: dict[str, Any]) -> bool:
    """有 pending 时判定本轮是否换题（而非补槽）。不依赖具体行业实体表。"""
    q = (question or "").strip()
    if not q:
        return False
    if _CANCEL.match(q):
        return True

    filled = pending.get("filled_slots") or {}
    entity = str(filled.get("entity") or "").strip()
    residue = _content_residue(q)
    original = str(pending.get("original_question") or "").strip()
    orig_residue = _content_residue(original)

    # 纯时间/指标补槽：去掉时间指标后无实质内容 → 不换题
    if not residue:
        return False

    # 完整新问句（自带时间+指标）：与原 pending 问句残差分叉 → 换题
    # 覆盖 filled.entity 为空时「销售额澄清中又来学生人数完整问句」的串台
    if _TIME.search(q) and _METRIC.search(q) and len(q) >= 8:
        if original and q != original and original not in q and q not in original:
            if _residues_diverged(residue, orig_residue):
                return True
        if entity and entity not in q and residue != entity:
            return True

    # 半截新对象 + 指标：残差存在且与 pending 实体不同
    if entity and entity not in q and residue != entity and _METRIC.search(q):
        return True

    return False
