"""Excel/CSV → 本地 SQLite 镜像（问数执行走 sqlite+aiosqlite）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.system.connectors.base import ConnectParams, ProbeResult

ROOT_DIR = Path(__file__).resolve().parents[3]  # backend/
EXCEL_DATA_DIR = ROOT_DIR / "data" / "excel_ds"


def sqlite_features(server_version: str | None = None) -> frozenset[str]:
    return frozenset({"select", "join", "subquery", "group_by", "cte", "window"})


class ExcelCsvConnector:
    """
    连接语义：
    - database：Excel/CSV 文件绝对或相对路径
    - host/port/user/password：可忽略（表单可空）
    - options.sqlite_path：可选，指定镜像库路径
    """

    db_type = "excel"
    dialect = "sqlite"
    sqlglot_read = "sqlite"
    sqlglot_dialect = "sqlite"
    display_name = "本地 Excel/CSV"
    uses_async_engine = True

    def _resolve_source_path(self, params: ConnectParams) -> Path:
        raw = (params.database or "").strip() or str(params.options.get("file_path") or "")
        path = Path(raw)
        if not path.is_absolute():
            path = (ROOT_DIR / path).resolve()
        return path

    def _mirror_path(self, params: ConnectParams) -> Path:
        custom = params.options.get("sqlite_path")
        if custom:
            p = Path(str(custom))
            return p if p.is_absolute() else (ROOT_DIR / p).resolve()
        src = self._resolve_source_path(params)
        digest = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:12]
        EXCEL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return EXCEL_DATA_DIR / f"{src.stem}_{digest}.sqlite"

    def build_sqlalchemy_url(self, params: ConnectParams) -> str:
        mirror = self._mirror_path(params)
        mirror.parent.mkdir(parents=True, exist_ok=True)
        # aiosqlite 需要三斜杠绝对路径
        return f"sqlite+aiosqlite:///{mirror.as_posix()}"

    async def ensure_mirror(self, params: ConnectParams) -> Path:
        """将 Excel/CSV 导入 SQLite（表名=sheet 名或 file stem）。"""
        import asyncio

        return await asyncio.to_thread(self._ensure_mirror_sync, params)

    def _ensure_mirror_sync(self, params: ConnectParams) -> Path:
        import pandas as pd
        from sqlalchemy import create_engine

        src = self._resolve_source_path(params)
        if not src.exists():
            raise FileNotFoundError(f"文件不存在：{src}")

        mirror = self._mirror_path(params)
        # 源更新则重建
        if mirror.exists() and mirror.stat().st_mtime >= src.stat().st_mtime:
            return mirror

        sync_url = f"sqlite:///{mirror.as_posix()}"
        engine = create_engine(sync_url)
        suffix = src.suffix.lower()
        try:
            if suffix in (".xlsx", ".xls"):
                sheets = pd.read_excel(src, sheet_name=None, engine="openpyxl")
                with engine.begin() as conn:
                    for sheet_name, df in sheets.items():
                        table = _safe_table_name(str(sheet_name))
                        df.to_sql(table, conn, if_exists="replace", index=False)
            elif suffix == ".csv":
                df = pd.read_csv(src)
                table = _safe_table_name(src.stem)
                with engine.begin() as conn:
                    df.to_sql(table, conn, if_exists="replace", index=False)
            else:
                raise ValueError(f"不支持的文件类型：{suffix}（仅 .xlsx/.xls/.csv）")
        finally:
            engine.dispose()
        return mirror

    async def probe(self, params: ConnectParams) -> ProbeResult:
        try:
            import aiosqlite  # noqa: F401
            import pandas  # noqa: F401
        except ImportError as e:
            return ProbeResult(ok=False, message=f"缺少依赖：{e}")

        try:
            mirror = await self.ensure_mirror(params)
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(self.build_sqlalchemy_url(params), pool_pre_ping=True)
            try:
                async with engine.connect() as conn:
                    rows = await conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                    tables = [r[0] for r in rows.fetchall()]
                return ProbeResult(
                    ok=True,
                    message=f"连通成功，已导入 {len(tables)} 张表 → {mirror.name}",
                    server_version="sqlite3",
                )
            finally:
                await engine.dispose()
        except Exception as e:
            return ProbeResult(ok=False, message=str(e)[:300])

    async def detect_version(self, params: ConnectParams) -> str | None:
        result = await self.probe(params)
        return result.server_version if result.ok else None

    def features_for_version(self, server_version: str | None) -> frozenset[str]:
        return sqlite_features(server_version)

    def prompt_dialect_label(self, server_version: str | None) -> str:
        return f"{self.display_name}（SQLite 镜像，支持 CTE/窗口函数）"


def _safe_table_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:64]
