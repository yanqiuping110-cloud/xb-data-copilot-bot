"""
有效描述合并：人工定义优先于业务库自动备注。
"""


def effective_description(manual: str | None, auto: str | None) -> str | None:
    """人工非空时优先，否则回退 auto。"""
    if manual is not None and manual.strip():
        return manual.strip()
    if auto is not None and auto.strip():
        return auto.strip()
    return None
