"""封面/结尾背景图列表与安全路径解析。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from config.settings import Settings, get_settings

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def backgrounds_root(settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    path = Path(cfg.brief_report_backgrounds_dir)
    if path.is_absolute():
        return path
    from config.settings import ROOT_DIR

    return ROOT_DIR / path


def _safe_relative(rel: str) -> str | None:
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or ".." in raw.split("/"):
        return None
    parts = [p for p in raw.split("/") if p]
    if len(parts) != 2:
        return None
    kind, name = parts
    if kind not in ("cover", "ending"):
        return None
    if Path(name).name != name:
        return None
    if Path(name).suffix.lower() not in _IMAGE_EXTS:
        return None
    return f"{kind}/{name}"


def resolve_background_path(rel: str, *, settings: Settings | None = None) -> Path | None:
    """将相对路径解析为绝对文件路径；不存在则 None。"""
    safe = _safe_relative(rel)
    if not safe:
        return None
    full = backgrounds_root(settings) / safe
    return full if full.is_file() else None


def list_backgrounds(*, settings: Settings | None = None) -> dict[str, list[dict[str, Any]]]:
    root = backgrounds_root(settings)
    out: dict[str, list[dict[str, Any]]] = {"cover": [], "ending": []}
    for kind in ("cover", "ending"):
        folder = root / kind
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in _IMAGE_EXTS:
                continue
            rel = f"{kind}/{f.name}"
            out[kind].append(
                {
                    "path": rel,
                    "name": f.stem,
                    "thumbnailUrl": (
                        f"/api/v1/ask/brief-report/backgrounds/file?path={quote(rel, safe='/')}"
                    ),
                }
            )
    return out


def default_backgrounds(theme: dict[str, Any], *, settings: Settings | None = None) -> tuple[str | None, str | None]:
    bg = theme.get("backgrounds") or {}
    cover = _safe_relative(bg.get("defaultCover") or "")
    ending = _safe_relative(bg.get("defaultEnding") or "")
    if cover and not resolve_background_path(cover, settings=settings):
        cover = None
    if ending and not resolve_background_path(ending, settings=settings):
        ending = None
    listed = list_backgrounds(settings=settings)
    if not cover and listed["cover"]:
        cover = listed["cover"][0]["path"]
    if not ending and listed["ending"]:
        ending = listed["ending"][0]["path"]
    return cover, ending
