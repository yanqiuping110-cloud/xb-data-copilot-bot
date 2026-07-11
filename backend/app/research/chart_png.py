"""chart_spec + 查询结果 → PNG（SSR 优先，matplotlib 降级）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.chart.ssr_client import render_chart_to_path_sync


def render_chart_png(
    *,
    chart_spec: dict[str, Any] | None,
    columns: list[str] | None,
    rows: list[list[Any]] | None,
    output_path: Path,
    title: str | None = None,
    settings: Any | None = None,
) -> str | None:
    """渲染 ChartSpec 为 PNG（委托 ssr_client）。"""
    return render_chart_to_path_sync(
        chart_spec=chart_spec,
        columns=columns,
        rows=rows,
        output_path=output_path,
        title=title,
        settings=settings,
    )
