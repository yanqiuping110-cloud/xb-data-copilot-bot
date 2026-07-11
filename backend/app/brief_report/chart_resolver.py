"""traceId → 章节图表 PNG 路径。"""

from __future__ import annotations

import shutil
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
    """
    返回章节图表 PNG 绝对路径；失败返回 None。

    优先复用 storage/charts/{trace_id}.png，否则在 work_dir 重渲染。
    """
    cfg = settings or get_settings()
    cached = cfg.chart_storage_path / f"{trace_id}.png"
    dest = work_dir / f"{trace_id}.png"
    work_dir.mkdir(parents=True, exist_ok=True)

    if cached.is_file():
        shutil.copy2(cached, dest)
        return str(dest)

    if not chart_spec or not columns or not rows:
        return None

    rendered = render_chart_png(
        chart_spec=chart_spec,
        columns=columns,
        rows=rows,
        output_path=dest,
        title=title,
        settings=cfg,
    )
    return rendered
