"""Chart 统一渲染（SSR 客户端 + 本地降级）。"""

from app.chart.ssr_client import render_chart_to_path

__all__ = ["render_chart_to_path"]
