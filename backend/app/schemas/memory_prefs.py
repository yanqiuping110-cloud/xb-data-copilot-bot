"""
用户偏好 Memory API 模型。
"""

from app.schemas.base import CamelModel


class PreferenceItem(CamelModel):
    """单条偏好。"""

    pref_key: str
    pref_value: dict | list | str | int | float | bool | None = None
    source: str = "explicit"


class PreferenceListResponse(CamelModel):
    """GET /memory/preferences 响应。"""

    items: list[PreferenceItem]


class PreferenceUpsertRequest(CamelModel):
    """PUT /memory/preferences 请求。"""

    preferences: dict[str, dict | list | str | int | float | bool | None]
