"""Brief Report 主题加载。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

THEMES_DIR = Path(__file__).resolve().parent / "themes"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache
def load_theme(name: str = "presentation") -> dict[str, Any]:
    path = THEMES_DIR / f"{name}.yaml"
    if not path.is_file():
        path = THEMES_DIR / "presentation.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
