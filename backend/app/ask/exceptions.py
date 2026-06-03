"""
问数业务异常（未匹配问句、SQL 执行失败等）。
"""

from __future__ import annotations


class AskError(Exception):
    """问数链路业务错误，映射为 4xx JSON。"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
