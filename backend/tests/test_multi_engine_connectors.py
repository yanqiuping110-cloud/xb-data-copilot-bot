"""多引擎连接器注册与方言校验单测。"""

from __future__ import annotations

import asyncio

from app.system.connectors import registry
from app.system.connectors.base import ConnectParams
from app.system.connectors.excel import ExcelCsvConnector
from app.system.models import ResolvedBusinessDsn
from app.system.sql_context import build_sql_context_from_dsn
from app.sql.dialect import parse_sql, render_sql


def test_all_planned_engines_registered():
    for code in (
        "mysql",
        "postgresql",
        "sqlserver",
        "oracle",
        "clickhouse",
        "doris",
        "starrocks",
        "excel",
    ):
        assert registry.is_available(code), (
            f"{code} should be registered, reason={registry.unavailable_reason(code)}"
        )


def test_dialect_roundtrip_select_limit():
    cases = [
        ("mysql", "5.7.44", "SELECT id FROM t", "LIMIT"),
        ("postgresql", "16.2", "SELECT id FROM t", "LIMIT"),
        ("sqlserver", "Microsoft SQL Server 2019", "SELECT id FROM t", ("TOP", "FETCH")),
        ("oracle", "Oracle Database 19c Enterprise Edition", "SELECT id FROM dual", "FETCH"),
        ("clickhouse", "24.1", "SELECT id FROM t", "LIMIT"),
        ("excel", "sqlite3", "SELECT id FROM t", "LIMIT"),
    ]
    for db_type, ver, sql, expect_kw in cases:
        dsn = ResolvedBusinessDsn(
            host="h",
            port=1,
            user="u",
            password="p",
            database="d",
            db_type=db_type,
            server_version=ver,
        )
        ctx = build_sql_context_from_dsn(dsn)
        parsed = parse_sql(sql, sql_ctx=ctx)
        limited = parsed.limit(10) if hasattr(parsed, "limit") else parsed
        out = render_sql(limited, sql_ctx=ctx)
        assert out
        upper = out.upper()
        if isinstance(expect_kw, tuple):
            assert any(k in upper for k in expect_kw), f"{db_type}: expected {expect_kw} in {out!r}"
        else:
            assert expect_kw in upper, f"{db_type}: expected {expect_kw} in {out!r}"
        parse_sql(out, sql_ctx=ctx)


def test_prompt_label_not_hardcoded_mysql():
    dsn = ResolvedBusinessDsn(
        host="h",
        port=5432,
        user="u",
        password="p",
        database="d",
        db_type="postgresql",
        server_version="16.2",
    )
    ctx = build_sql_context_from_dsn(dsn)
    assert "PostgreSQL" in ctx.prompt_dialect_label
    assert "MySQL 5.7" not in ctx.prompt_dialect_label


def test_excel_features_include_cte():
    dsn = ResolvedBusinessDsn(
        host="local",
        port=0,
        user="file",
        password="",
        database="demo.xlsx",
        db_type="excel",
        server_version="sqlite3",
    )
    ctx = build_sql_context_from_dsn(dsn)
    assert ctx.supports_cte
    assert ctx.sqlglot_read == "sqlite"


def test_catalog_selectable_matches_registry():
    from app.system import catalog_loader as cl
    from app.system.catalog_loader import is_datasource_selectable, list_datasource_types

    cl._llm_providers_raw.cache_clear()
    cl._datasource_types_raw.cache_clear()

    for t in list_datasource_types():
        code = t["code"]
        if t.get("selectable"):
            assert is_datasource_selectable(code) == registry.is_available(code)


def test_excel_probe_missing_file():
    conn = ExcelCsvConnector()
    result = asyncio.get_event_loop().run_until_complete(
        conn.probe(
            ConnectParams(
                host="local",
                port=0,
                database="__missing_no_such_file__.xlsx",
                user="file",
                password="",
            )
        )
    )
    assert result.ok is False


def test_excel_probe_csv_roundtrip(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")
    conn = ExcelCsvConnector()
    result = asyncio.get_event_loop().run_until_complete(
        conn.probe(
            ConnectParams(
                host="local",
                port=0,
                database=str(csv_path),
                user="file",
                password="",
            )
        )
    )
    assert result.ok, result.message
    assert result.server_version == "sqlite3"
