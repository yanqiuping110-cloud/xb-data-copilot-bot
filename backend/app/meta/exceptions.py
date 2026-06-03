"""元数据 API 业务异常。"""


class MetaError(Exception):
    """元数据/introspect 错误。"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
