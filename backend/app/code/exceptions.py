"""代码知识库业务异常。"""

from __future__ import annotations


class CodeKnowledgeError(Exception):
    """代码知识库操作失败。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
