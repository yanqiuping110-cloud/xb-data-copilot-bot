"""traceId → 章节图表 PNG 路径。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.research.chart_png import render_chart_png
from config.settings import Settings, get_settings


def resolve_chart_png(
    *,
    trace_id: str,
    chart_spec: dict[str, Any] | None,
    columns: list[str] | None,
    rows: list[list[Any]] | None,
    title: str | None,
    work_dir: Path,
    settings: Settings | None = None,
) -> str | None:
    """返回章节图表 PNG 绝对路径；使用 ECharts SSR 与页面同款样式。"""
    if not chart_spec or not columns or not rows:
        return None

    cfg = settings or get_settings()
    dest = work_dir / f"{trace_id}.png"
    work_dir.mkdir(parents=True, exist_ok=True)

    return render_chart_png(
        chart_spec=chart_spec,
        columns=columns,
        rows=rows,
        output_path=dest,
        title=title,
        settings=cfg,
    )
