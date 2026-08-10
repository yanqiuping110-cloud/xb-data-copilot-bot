"""系统配置 API 业务异常。"""


class SystemConfigError(Exception):
    """LLM / 数据源配置错误。"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
