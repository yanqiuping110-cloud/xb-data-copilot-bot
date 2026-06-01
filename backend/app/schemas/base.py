"""
API 请求/响应模型基类。

JSON 字段使用 camelCase（与前端、DEVELOPMENT_PLAN §10 一致），
Python 属性仍用 snake_case，通过 alias_generator 映射。
"""

from pydantic import BaseModel, ConfigDict


def to_camel(name: str) -> str:
    """snake_case → camelCase，供 Pydantic alias 使用。"""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class CamelModel(BaseModel):
    """对外 API 模型的基类。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # 同时接受 snake 与 camel 入参
    )
