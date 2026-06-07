"""
问句关键词抽取：规则分词，ES 不可用时降级为整句检索。
"""

from __future__ import annotations

import re

# 常见虚词，不参与召回匹配
_STOP_WORDS = frozenset(
    {
        "的",
        "了",
        "是",
        "在",
        "有",
        "和",
        "与",
        "或",
        "及",
        "吗",
        "呢",
        "吧",
        "啊",
        "多少",
        "什么",
        "怎么",
        "如何",
        "哪个",
        "哪些",
        "请问",
        "查询",
        "统计",
        "显示",
        "查看",
        "本校",
        "学校",
        "最近",
        "本月",
        "本周",
        "今天",
        "昨天",
        "the",
        "a",
        "an",
        "is",
        "are",
        "what",
        "how",
    }
)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z_][a-zA-Z0-9_]{1,}")


def _split_chinese_phrases(text: str, *, max_len: int = 6) -> list[str]:
    """长中文连续串切分为 2～4 字短语，避免整句被当成一个 token。"""
    phrases: list[str] = []
    if len(text) <= max_len:
        return [text]
    for size in (4, 3, 2):
        for i in range(0, len(text) - size + 1):
            phrases.append(text[i : i + size])
    return phrases


def _extract_short_chinese_bigrams(text: str) -> list[str]:
    """从问句提取全部连续 2 字中文片段，优先保留业务实体词（如「跳绳」）。"""
    found: list[str] = []
    seen: set[str] = set()
    for i in range(len(text) - 1):
        if not ("\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff"):
            continue
        token = text[i : i + 2]
        if token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        found.append(token)
    return found


def extract_keywords(question: str, *, max_keywords: int = 12) -> list[str]:
    """
    从问句抽取关键词列表。

    优先保留 2 字以上中文词与英文标识符；无有效词时返回整句（去首尾空白）。
    """
    q = (question or "").strip()
    if not q:
        return []

    for suffix in ("是多少", "有多少", "怎么样", "如何", "吗", "呢", "？"):
        q = q.replace(suffix, " ")

    tokens: list[str] = []
    seen: set[str] = set()

    # 先放入全部 2 字中文片段，避免长句 n-gram 挤掉「跳绳」等领域词
    for token in _extract_short_chinese_bigrams(q):
        seen.add(token)
        tokens.append(token)

    for match in _TOKEN_RE.finditer(q):
        raw = match.group(0)
        candidates = _split_chinese_phrases(raw) if len(raw) > 6 and not raw.isascii() else [raw]
        for token in candidates:
            norm = token.lower() if token.isascii() else token
            if norm in _STOP_WORDS or norm in seen or len(norm) < 2:
                continue
            seen.add(norm)
            tokens.append(norm)

    if not tokens:
        return [(question or "").strip()[:200]]

    return tokens[:max_keywords]
