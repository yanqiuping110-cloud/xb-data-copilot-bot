"""
用户偏好 key 白名单。

仅 explicit 来源且 key 在白名单内的偏好可注入 Prompt。
"""

from __future__ import annotations

# 允许运营/用户设置的偏好键
PREFERENCE_KEY_WHITELIST: frozenset[str] = frozenset(
    {
        "default_time_range",
        "preferred_grain",
        "column_alias_hints",
        "answer_style",
    }
)


def is_allowed_pref_key(key: str) -> bool:
    """校验偏好 key 是否在白名单内。"""
    return key in PREFERENCE_KEY_WHITELIST
