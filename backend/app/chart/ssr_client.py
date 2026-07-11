"""ChartSpec → PNG：优先 SSR 服务，失败降级本地渲染。"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from app.chart.local_renderer import render_chart_local
from config.settings import Settings, get_settings

logger = logging.getLogger("chart.ssr")

_CACHE: dict[str, str] = {}


def _cache_key(spec: dict[str, Any], columns: list[str], rows: list[list[Any]]) -> str:
    payload = json.dumps(
        {"spec": spec, "columns": columns, "rows": rows[:30]},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _decode_render_response(data: dict[str, Any]) -> bytes | None:
    b64 = data.get("pngBase64") or data.get("png_base64")
    if b64:
        return base64.b64decode(b64)
    svg_b64 = data.get("svgBase64") or data.get("svg_base64")
    if svg_b64:
        try:
            import cairosvg

            return cairosvg.svg2png(bytestring=base64.b64decode(svg_b64))
        except Exception:
            logger.debug("SVG→PNG 转换不可用，降级本地渲染")
    path = data.get("pngPath")
    if path and Path(path).is_file():
        return Path(path).read_bytes()
    return None


async def _render_via_http(
    *,
    url: str,
    chart_spec: dict[str, Any],
    columns: list[str],
    rows: list[list[Any]],
    title: str | None,
    width: int,
    height: int,
    timeout_ms: int,
    api_key: str | None,
) -> bytes | None:
    endpoint = url.rstrip("/") + "/render"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Chart-Ssr-Key"] = api_key
    body = {
        "chartSpec": chart_spec,
        "columns": columns,
        "rows": rows[:50],
        "title": title,
        "width": width,
        "height": height,
        "format": "png",
    }
    async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
        resp = await client.post(endpoint, json=body, headers=headers)
        resp.raise_for_status()
        return _decode_render_response(resp.json())


def _render_via_http_sync(
    *,
    url: str,
    chart_spec: dict[str, Any],
    columns: list[str],
    rows: list[list[Any]],
    title: str | None,
    width: int,
    height: int,
    timeout_ms: int,
    api_key: str | None,
) -> bytes | None:
    endpoint = url.rstrip("/") + "/render"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Chart-Ssr-Key"] = api_key
    body = {
        "chartSpec": chart_spec,
        "columns": columns,
        "rows": rows[:50],
        "title": title,
        "width": width,
        "height": height,
        "format": "png",
    }
    with httpx.Client(timeout=timeout_ms / 1000) as client:
        resp = client.post(endpoint, json=body, headers=headers)
        resp.raise_for_status()
        return _decode_render_response(resp.json())


def render_chart_to_path_sync(
    *,
    chart_spec: dict[str, Any] | None,
    columns: list[str] | None,
    rows: list[list[Any]] | None,
    output_path: Path,
    title: str | None = None,
    settings: Settings | None = None,
) -> str | None:
    """同步入口（research PDF 等同步上下文）。"""
    cfg = settings or get_settings()
    if not columns or not rows:
        return None

    spec = dict(chart_spec or {})
    if spec.get("status") == "rejected":
        return None

    cache_key = _cache_key(spec, columns, rows)
    if cache_key in _CACHE and Path(_CACHE[cache_key]).is_file():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(Path(_CACHE[cache_key]).read_bytes())
        return str(output_path)

    if cfg.chart_ssr_enabled and cfg.chart_ssr_url:
        try:
            png = _render_via_http_sync(
                url=cfg.chart_ssr_url,
                chart_spec=spec,
                columns=columns,
                rows=rows,
                title=title,
                width=cfg.chart_ssr_width,
                height=cfg.chart_ssr_height,
                timeout_ms=cfg.chart_ssr_timeout_ms,
                api_key=cfg.chart_ssr_api_key or None,
            )
        except Exception as exc:
            logger.warning("Chart SSR failed: %s", exc)
            png = None
        if png:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(png)
            _CACHE[cache_key] = str(output_path)
            return str(output_path)

    rendered = render_chart_local(
        chart_spec=spec,
        columns=columns,
        rows=rows,
        output_path=output_path,
        title=title,
        width=cfg.chart_ssr_width,
        height=cfg.chart_ssr_height,
    )
    if rendered:
        _CACHE[cache_key] = rendered
    return rendered


async def render_chart_to_path(
    *,
    chart_spec: dict[str, Any] | None,
    columns: list[str] | None,
    rows: list[list[Any]] | None,
    output_path: Path,
    title: str | None = None,
    settings: Settings | None = None,
) -> str | None:
    """异步入口。"""
    cfg = settings or get_settings()
    if not columns or not rows:
        return None

    spec = dict(chart_spec or {})
    if spec.get("status") == "rejected":
        return None

    if cfg.chart_ssr_enabled and cfg.chart_ssr_url:
        try:
            png = await _render_via_http(
                url=cfg.chart_ssr_url,
                chart_spec=spec,
                columns=columns,
                rows=rows,
                title=title,
                width=cfg.chart_ssr_width,
                height=cfg.chart_ssr_height,
                timeout_ms=cfg.chart_ssr_timeout_ms,
                api_key=cfg.chart_ssr_api_key or None,
            )
            if png:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(png)
                return str(output_path)
        except Exception as exc:
            logger.warning("Chart SSR failed, fallback local: %s", exc)

    return render_chart_local(
        chart_spec=spec,
        columns=columns,
        rows=rows,
        output_path=output_path,
        title=title,
        width=cfg.chart_ssr_width,
        height=cfg.chart_ssr_height,
    )
