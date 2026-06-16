"""SQL 网关异常定义。"""


class SqlGuardError(Exception):
    """SQL 校验或策略拒绝。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
