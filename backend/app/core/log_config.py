"""
应用日志配置：问数 LangGraph 节点与异常统一输出到终端 stderr。

对 copilot 命名空间单独挂载带 flush 的 StreamHandler，避免 uvicorn reload 下日志不可见。
"""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured = False


class _FlushingStreamHandler(logging.StreamHandler):
    """每次 emit 后立即 flush，确保 VS Code / uvicorn 终端即时可见。"""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def setup_logging(*, debug: bool = True) -> None:
    """初始化 copilot 日志（幂等，可重复调用）。"""
    global _configured
    level = logging.DEBUG if debug else logging.INFO

    copilot = logging.getLogger("copilot")
    copilot.setLevel(level)
    copilot.propagate = False

    if not copilot.handlers:
        handler = _FlushingStreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
        copilot.addHandler(handler)
    else:
        for handler in copilot.handlers:
            handler.setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    if not _configured:
        logging.getLogger("copilot.boot").info(
            "copilot 日志已启用（stderr）；问数节点日志格式 [trace=...] 中文含义[node名] status=中文[英文] ..."
        )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取 copilot 命名空间下的 logger。"""
    if not _configured:
        setup_logging(debug=True)
    if name.startswith("copilot."):
        return logging.getLogger(name)
    return logging.getLogger(f"copilot.{name}")
