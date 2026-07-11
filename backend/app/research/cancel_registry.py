"""进行中的报告取消标记（进程内，单实例）。"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cancelled: set[str] = set()


def request_cancel(report_id: str) -> None:
    with _lock:
        _cancelled.add(report_id)


def is_cancelled(report_id: str) -> bool:
    with _lock:
        return report_id in _cancelled


def clear_cancel(report_id: str) -> None:
    with _lock:
        _cancelled.discard(report_id)
