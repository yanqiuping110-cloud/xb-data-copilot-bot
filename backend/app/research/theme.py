"""Theme Pack 加载与 CSS 变量。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

THEMES_DIR = Path(__file__).resolve().parent / "themes"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache
def load_theme(name: str = "default") -> dict[str, Any]:
    path = THEMES_DIR / f"{name}.yaml"
    if not path.is_file():
        path = THEMES_DIR / "default.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def accent_for_intent(theme: dict[str, Any], intent: str | None) -> str:
    mapping = (theme.get("accentByIntent") or {}) if theme else {}
    key = (intent or "open_query").lower()
    return mapping.get(key) or mapping.get("open_query") or "#6366f1"
