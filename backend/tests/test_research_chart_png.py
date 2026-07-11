"""chart_png 离线单测。"""

from pathlib import Path

from app.research.chart_png import render_chart_png


def test_render_chart_png_bar(tmp_path: Path):
    out = tmp_path / "chart.png"
    path = render_chart_png(
        chart_spec={"chartType": "bar", "xColumn": "A", "yColumns": ["B"], "status": "ready"},
        columns=["A", "B"],
        rows=[["x1", 10], ["x2", 20], ["x3", 15]],
        output_path=out,
        title="测试图",
    )
    assert path is not None
    assert out.is_file()
    assert out.stat().st_size > 500
