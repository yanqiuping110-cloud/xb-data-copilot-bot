"""ChartSpec 本地 PNG 渲染（matplotlib，SSR 降级路径）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# 中文字体 fallback（Windows / Linux 常见字体）
_CJK_FONTS = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans"]


def _configure_cjk_font() -> None:
    for name in _CJK_FONTS:
        try:
            plt.rcParams["font.sans-serif"] = [name] + plt.rcParams.get("font.sans-serif", [])
            plt.rcParams["axes.unicode_minus"] = False
            return
        except Exception:
            continue


def render_chart_local(
    *,
    chart_spec: dict[str, Any] | None,
    columns: list[str] | None,
    rows: list[list[Any]] | None,
    output_path: Path,
    title: str | None = None,
    width: int = 720,
    height: int = 400,
) -> str | None:
    """渲染 ChartSpec 为 PNG 文件。"""
    if not columns or not rows:
        return None
    spec = chart_spec or {}
    if spec.get("status") == "rejected":
        return None

    chart_type = spec.get("chartType") or spec.get("chart_type") or "bar"
    x_col = spec.get("xColumn") or spec.get("x_column")
    y_cols = spec.get("yColumns") or spec.get("y_columns") or []

    col_idx = {c: i for i, c in enumerate(columns)}
    if not x_col or x_col not in col_idx:
        x_col = columns[0]
    if not y_cols:
        y_cols = [c for c in columns if c != x_col][:1]
    y_cols = [c for c in y_cols if c in col_idx]
    if not y_cols:
        return None

    _configure_cjk_font()
    xi = col_idx[x_col]
    x_vals = [str(row[xi]) if xi < len(row) else "" for row in rows[:30]]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dpi = 120
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor("#ffffff")
    colors = ["#6366f1", "#8b5cf6", "#06b6d4"]
    for i, yc in enumerate(y_cols[:3]):
        yi = col_idx[yc]
        y_vals = []
        for row in rows[:30]:
            try:
                y_vals.append(float(row[yi]) if yi < len(row) and row[yi] is not None else 0)
            except (TypeError, ValueError):
                y_vals.append(0)
        color = colors[i % len(colors)]
        if chart_type in ("line", "area", "trend"):
            ax.plot(range(len(x_vals)), y_vals, marker="o", label=yc, linewidth=2, color=color)
            if chart_type == "area":
                ax.fill_between(range(len(x_vals)), y_vals, alpha=0.15, color=color)
        elif chart_type == "pie" and len(y_vals) <= 12:
            ax.pie(y_vals, labels=x_vals, autopct="%1.0f%%", textprops={"fontsize": 7})
            ax.set_title(title or spec.get("title") or "图表", fontsize=11)
            fig.tight_layout()
            fig.savefig(output_path, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            return str(output_path)
        else:
            ax.bar(range(len(x_vals)), y_vals, label=yc, alpha=0.88, color=color)

    ax.set_title(title or spec.get("title") or "图表", fontsize=11, color="#0f172a")
    ax.set_xticks(range(len(x_vals)))
    ax.set_xticklabels(x_vals, rotation=35, ha="right", fontsize=8)
    ax.legend(fontsize=8, loc="upper right", framealpha=0.9)
    ax.grid(True, alpha=0.2, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(output_path)
