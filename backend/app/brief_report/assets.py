"""报告资源：图片转 data URI / 本地路径。"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any


def path_to_data_uri(path: str | Path | None) -> str | None:
    p = Path(path) if path else None
    if not p or not p.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(p))
    if not mime:
        mime = "image/png"
    encoded = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def enrich_doc_assets(doc: dict[str, Any]) -> dict[str, Any]:
    """为 HTML/备用渲染注入 data URI，避免 WeasyPrint file:// 在 Windows 失效。"""
    out = dict(doc)
    cover = dict(out.get("cover") or {})
    ending = dict(out.get("ending") or {})
    if cover.get("backgroundPath"):
        cover["backgroundDataUri"] = path_to_data_uri(cover["backgroundPath"])
    if ending.get("backgroundPath"):
        ending["backgroundDataUri"] = path_to_data_uri(ending["backgroundPath"])
    out["cover"] = cover
    out["ending"] = ending

    chapters: list[dict[str, Any]] = []
    for ch in out.get("chapters") or []:
        item = dict(ch)
        if item.get("chartPngPath"):
            item["chartDataUri"] = path_to_data_uri(item["chartPngPath"])
        chapters.append(item)
    out["chapters"] = chapters
    return out
