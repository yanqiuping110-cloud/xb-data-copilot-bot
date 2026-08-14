"""
开源 Demo 一键初始化：DDL → admin → ShopPulse xlsx → meta → 默认 excel 数据源。

用法（backend/）:
  $env:APP_ENV = "demo"
  python scripts/bootstrap_demo.py --profile excel
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _repo_root(settings) -> Path:
    if settings.demo_root.strip():
        return Path(settings.demo_root).resolve()
    cand = ROOT.parent
    if (cand / "demo").is_dir():
        return cand
    return ROOT


def _ready_marker(repo: Path) -> Path:
    # Prefer writable .demo under workspace; fallback /app/data
    for p in (repo / ".demo", ROOT / "data" / "demo"):
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p / "ready"
        except OSError:
            continue
    return ROOT / "DEMO_READY"


async def wait_mysql(url: str, *, timeout_sec: int = 120) -> None:
    engine = create_async_engine(url, echo=False)
    deadline = time.time() + timeout_sec
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            await asyncio.sleep(2)
    await engine.dispose()
    raise RuntimeError(f"MySQL not ready within {timeout_sec}s: {last_err}")


async def apply_ddl(url: str, database: str) -> None:
    import importlib.util

    engine = create_async_engine(url, echo=False)
    async with engine.connect() as conn:
        try:
            await conn.execute(text("SELECT 1 FROM copilot_sys_user LIMIT 1"))
            print("[bootstrap] DDL skipped (copilot_sys_user exists)")
            await engine.dispose()
            return
        except Exception:
            pass

    ddl_path = ROOT / "scripts" / "apply_ddl_to_env_db.py"
    spec = importlib.util.spec_from_file_location("apply_ddl_to_env_db", ddl_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    files = mod._version_files()
    total = 0
    async with engine.begin() as conn:
        for vf in files:
            for stmt in mod._statements_from_file(vf, database):
                try:
                    await conn.execute(text(stmt))
                    total += 1
                except Exception as exc:  # noqa: BLE001 — idempotent-ish for re-runs
                    print(f"[bootstrap] skip stmt in {vf.name}: {exc}")
            print(f"[bootstrap] DDL {vf.name}")
    await engine.dispose()
    print(f"[bootstrap] DDL done ({total} statements)")


async def seed_admin(url: str, username: str, password: str) -> None:
    engine = create_async_engine(url, echo=False)
    password_hash = pwd_context.hash(password)
    async with engine.begin() as conn:
        row = await conn.execute(
            text(
                "SELECT id FROM copilot_sys_user WHERE username = :u AND deleted = 0 LIMIT 1"
            ),
            {"u": username},
        )
        existing = row.mappings().first()
        if existing:
            await conn.execute(
                text(
                    "UPDATE copilot_sys_user SET password_hash = :h, role = 'ADMIN', status = 1 "
                    "WHERE id = :id"
                ),
                {"h": password_hash, "id": int(existing["id"])},
            )
            print(f"[bootstrap] admin password refreshed: {username}")
        else:
            await conn.execute(
                text(
                    """
                    INSERT INTO copilot_sys_user
                      (username, password_hash, display_name, role, status, deleted)
                    VALUES
                      (:u, :h, 'Demo Admin', 'ADMIN', 1, 0)
                    """
                ),
                {"u": username, "h": password_hash},
            )
            print(f"[bootstrap] admin created: {username}")
    await engine.dispose()


def ensure_shop_pulse_xlsx(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    users = pd.DataFrame(
        [
            {"id": 1, "name": "Alice", "city": "Shanghai", "created_at": "2024-01-10"},
            {"id": 2, "name": "Bob", "city": "Beijing", "created_at": "2024-02-12"},
            {"id": 3, "name": "Carol", "city": "Shanghai", "created_at": "2024-03-01"},
            {"id": 4, "name": "Dave", "city": "Shenzhen", "created_at": "2024-03-15"},
            {"id": 5, "name": "Eve", "city": "Beijing", "created_at": "2024-04-02"},
            {"id": 6, "name": "Frank", "city": "Shanghai", "created_at": "2024-05-08"},
        ]
    )
    products = pd.DataFrame(
        [
            {"id": 1, "name": "Trail Shoe", "category": "Footwear", "price": 499.0},
            {"id": 2, "name": "Yoga Mat", "category": "Accessories", "price": 129.0},
            {"id": 3, "name": "Hoodie", "category": "Apparel", "price": 259.0},
            {"id": 4, "name": "Water Bottle", "category": "Accessories", "price": 59.0},
        ]
    )
    orders = pd.DataFrame(
        [
            {"id": 1, "user_id": 1, "product_id": 1, "qty": 1, "amount": 499.0, "order_date": "2024-06-01", "status": "paid"},
            {"id": 2, "user_id": 2, "product_id": 2, "qty": 2, "amount": 258.0, "order_date": "2024-06-03", "status": "paid"},
            {"id": 3, "user_id": 3, "product_id": 3, "qty": 1, "amount": 259.0, "order_date": "2024-06-05", "status": "shipped"},
            {"id": 4, "user_id": 1, "product_id": 4, "qty": 3, "amount": 177.0, "order_date": "2024-06-08", "status": "paid"},
            {"id": 5, "user_id": 4, "product_id": 1, "qty": 1, "amount": 499.0, "order_date": "2024-06-10", "status": "cancelled"},
            {"id": 6, "user_id": 5, "product_id": 3, "qty": 2, "amount": 518.0, "order_date": "2024-06-12", "status": "paid"},
            {"id": 7, "user_id": 6, "product_id": 2, "qty": 1, "amount": 129.0, "order_date": "2024-06-15", "status": "paid"},
            {"id": 8, "user_id": 2, "product_id": 4, "qty": 2, "amount": 118.0, "order_date": "2024-06-18", "status": "shipped"},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        users.to_excel(writer, sheet_name="users", index=False)
        products.to_excel(writer, sheet_name="products", index=False)
        orders.to_excel(writer, sheet_name="orders", index=False)
    print(f"[bootstrap] wrote {path}")
    return path


async def seed_meta_and_datasource(
    session: AsyncSession,
    *,
    seed_meta: dict,
    xlsx_path: Path,
) -> None:
    from app.system.datasource_repository import DatasourceRepository

    # tables + columns
    for t in seed_meta.get("tables") or []:
        table_name = t["table_name"]
        existing = await session.execute(
            text(
                "SELECT id FROM copilot_table_meta WHERE table_name = :n AND deleted = 0 LIMIT 1"
            ),
            {"n": table_name},
        )
        row = existing.mappings().first()
        if row:
            table_id = int(row["id"])
            await session.execute(
                text(
                    """
                    UPDATE copilot_table_meta SET
                      table_role = :role, biz_domain = :dom,
                      description_manual = :desc, status = 1
                    WHERE id = :id
                    """
                ),
                {
                    "role": t.get("table_role"),
                    "dom": t.get("biz_domain"),
                    "desc": t.get("description_manual"),
                    "id": table_id,
                },
            )
        else:
            result = await session.execute(
                text(
                    """
                    INSERT INTO copilot_table_meta (
                      table_name, table_role, biz_domain, description_manual,
                      sch_id_column, status, deleted
                    ) VALUES (
                      :n, :role, :dom, :desc, 'sch_id', 1, 0
                    )
                    """
                ),
                {
                    "n": table_name,
                    "role": t.get("table_role"),
                    "dom": t.get("biz_domain"),
                    "desc": t.get("description_manual"),
                },
            )
            table_id = int(result.lastrowid)

        for i, col in enumerate(t.get("columns") or []):
            cname = col["column_name"]
            found = await session.execute(
                text(
                    """
                    SELECT id FROM copilot_column_meta
                    WHERE table_id = :tid AND column_name = :cn AND deleted = 0 LIMIT 1
                    """
                ),
                {"tid": table_id, "cn": cname},
            )
            if found.mappings().first():
                continue
            await session.execute(
                text(
                    """
                    INSERT INTO copilot_column_meta (
                      table_id, column_name, ordinal_position, data_type,
                      description_manual, column_role, is_nullable, status,
                      recall_enabled, deleted
                    ) VALUES (
                      :tid, :cn, :ord, :dt, :desc, :role, 1, 1, 1, 0
                    )
                    """
                ),
                {
                    "tid": table_id,
                    "cn": cname,
                    "ord": i + 1,
                    "dt": col.get("data_type") or "TEXT",
                    "desc": col.get("description_manual"),
                    "role": col.get("column_role"),
                },
            )

    ds_cfg = seed_meta.get("datasource") or {}
    repo = DatasourceRepository(session)
    # Demo 仅保留 Excel 样例源：清掉问数库中既有业务源（避免 SQL/历史种子残留）
    await session.execute(
        text(
            """
            UPDATE copilot_business_datasource
            SET deleted = 1, is_default = 0
            WHERE deleted = 0
            """
        )
    )
    await repo.insert(
        name=str(ds_cfg.get("name") or "ShopPulse Excel Demo"),
        db_type="excel",
        host=str(ds_cfg.get("host") or "local"),
        port=int(ds_cfg.get("port") or 0),
        database_name=str(xlsx_path.resolve()),
        username=str(ds_cfg.get("username") or "demo"),
        password=str(ds_cfg.get("password") or ""),
        is_default=True,
        status=1,
    )
    await session.commit()
    print(f"[bootstrap] default datasource → {xlsx_path}")


async def run(profile: str) -> None:
    # Ensure settings reload with current APP_ENV
    get_settings.cache_clear()
    settings = get_settings()
    repo = _repo_root(settings)
    profile_dir = repo / "demo" / "profiles" / profile
    seed_meta_path = profile_dir / "seed_meta.json"
    if not seed_meta_path.is_file():
        raise FileNotFoundError(f"missing {seed_meta_path}")

    print(f"[bootstrap] waiting MySQL ({settings.mysql_copilot_host}) …")
    await wait_mysql(settings.copilot_database_url)

    await apply_ddl(settings.copilot_database_url, settings.mysql_copilot_database)
    await seed_admin(
        settings.copilot_database_url,
        settings.seed_admin_username,
        settings.seed_admin_password,
    )

    # Prefer writable data dir inside container; also write under profile if possible
    xlsx_candidates = [
        ROOT / "data" / "demo" / "shop_pulse.xlsx",
        profile_dir / "data" / "shop_pulse.xlsx",
    ]
    xlsx_path = xlsx_candidates[0]
    for cand in xlsx_candidates:
        try:
            cand.parent.mkdir(parents=True, exist_ok=True)
            xlsx_path = cand
            break
        except OSError:
            continue
    ensure_shop_pulse_xlsx(xlsx_path)

    seed_meta = json.loads(seed_meta_path.read_text(encoding="utf-8"))
    engine = create_async_engine(settings.copilot_database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_meta_and_datasource(session, seed_meta=seed_meta, xlsx_path=xlsx_path)
    await engine.dispose()

    # Refresh runtime caches if app already imported them (entrypoint order: bootstrap then uvicorn)
    try:
        from app.system.runtime_config import refresh_runtime_config
        from app.db.business import invalidate_business_engine

        refresh_runtime_config(settings)
        await invalidate_business_engine()
    except Exception as exc:  # noqa: BLE001
        print(f"[bootstrap] runtime refresh skipped: {exc}")

    marker = _ready_marker(repo)
    marker.write_text(
        json.dumps(
            {
                "ok": True,
                "profile": profile,
                "xlsx": str(xlsx_path),
                "admin": settings.seed_admin_username,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("DEMO_READY")
    print(f"[bootstrap] ready marker → {marker}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap opensource demo")
    parser.add_argument("--profile", default=os.getenv("DEMO_PROFILE", "excel"))
    args = parser.parse_args()
    asyncio.run(run(args.profile))


if __name__ == "__main__":
    main()
