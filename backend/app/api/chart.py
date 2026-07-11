"""Chart PNG 渲染与静态访问。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.chart.ssr_client import render_chart_to_path
from app.core.context import UserContext
from app.core.security import get_current_user
from config.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/chart", tags=["chart"])


class ChartRenderRequest(BaseModel):
    chart_spec: dict[str, Any] = Field(alias="chartSpec")
    columns: list[str]
    rows: list[list[Any]]
    title: str | None = None
    cache_key: str | None = Field(default=None, alias="cacheKey")

    model_config = {"populate_by_name": True}


class ChartRenderResponse(BaseModel):
    chart_image_url: str = Field(alias="chartImageUrl")
    cache_key: str = Field(alias="cacheKey")

    model_config = {"populate_by_name": True}


def _png_path(settings: Settings, cache_key: str) -> Path:
    safe = "".join(c for c in cache_key if c.isalnum() or c in "-_")[:64]
    return settings.chart_storage_path / f"{safe}.png"


@router.post("/render", response_model=ChartRenderResponse, response_model_by_alias=True)
async def render_chart(
    body: ChartRenderRequest,
    _: Annotated[UserContext, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChartRenderResponse:
    """将 ChartSpec 渲染为 PNG 并返回访问 URL。"""
    from app.chart.ssr_client import _cache_key

    key = body.cache_key or _cache_key(body.chart_spec, body.columns, body.rows)
    out = _png_path(settings, key)
    path = await render_chart_to_path(
        chart_spec=body.chart_spec,
        columns=body.columns,
        rows=body.rows,
        output_path=out,
        title=body.title,
        settings=settings,
    )
    if not path:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "CHART_RENDER_FAILED", "message": "无法渲染图表"}},
        )
    return ChartRenderResponse(
        chart_image_url=f"/api/v1/chart/png/{key}",
        cache_key=key,
    )


@router.get("/png/{cache_key}")
async def get_chart_png(
    cache_key: str,
    _: Annotated[UserContext, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    """读取已缓存的 Chart PNG。"""
    path = _png_path(settings, cache_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图表不存在")
    return FileResponse(path, media_type="image/png")
