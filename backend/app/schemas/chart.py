"""
图表规格 API 模型（与前端 ECharts 适配层对齐）。
"""

from app.schemas.base import CamelModel


class ChartSeriesSpec(CamelModel):
    """单条数据系列。"""

    name: str
    column: str
    type: str | None = None


class ChartSpec(CamelModel):
    """查询结果的可视化规格。"""

    chart_type: str = "none"
    title: str | None = None
    x_column: str | None = None
    y_columns: list[str] = []
    series: list[ChartSeriesSpec] | None = None
    options: dict | None = None
    status: str = "skipped"
    reject_reason: str | None = None
