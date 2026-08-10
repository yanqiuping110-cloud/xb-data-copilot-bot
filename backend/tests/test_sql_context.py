"""ResolvedSqlContext / 版本特性单测。"""

from __future__ import annotations

from app.system.connectors.mysql import mysql_connector
from app.system.connectors.postgresql import PostgresqlConnector
from app.system.connectors.version_features import mysql_family_features, postgres_features
from app.system.models import ResolvedBusinessDsn
from app.system.sql_context import build_sql_context_from_dsn


def test_mysql_57_features_conservative():
    feats = mysql_family_features("5.7.44")
    assert "cte" not in feats
    assert "window" not in feats
    label = mysql_connector().prompt_dialect_label("5.7.44")
    assert "MySQL" in label
    assert "5.7" in label
    assert "保守" in label or "避免" in label


def test_mysql_80_features_open():
    feats = mysql_family_features("8.0.36")
    assert "cte" in feats
    assert "window" in feats


def test_postgres_features():
    feats = postgres_features("16.2")
    assert "cte" in feats and "window" in feats
    label = PostgresqlConnector().prompt_dialect_label("16.2")
    assert "PostgreSQL" in label


def test_build_sql_context_from_dsn_mysql():
    dsn = ResolvedBusinessDsn(
        host="127.0.0.1",
        port=3306,
        user="u",
        password="p",
        database="db",
        db_type="mysql",
        server_version="5.7.44",
    )
    ctx = build_sql_context_from_dsn(dsn)
    assert ctx.db_type == "mysql"
    assert ctx.sqlglot_read == "mysql"
    assert not ctx.supports_cte
    assert "MySQL" in ctx.prompt_dialect_label


def test_aggregate_hint_differs_by_version():
    dsn57 = ResolvedBusinessDsn(
        host="h",
        port=3306,
        user="u",
        password="p",
        database="d",
        db_type="mysql",
        server_version="5.7.44",
    )
    dsn80 = ResolvedBusinessDsn(
        host="h",
        port=3306,
        user="u",
        password="p",
        database="d",
        db_type="mysql",
        server_version="8.0.36",
    )
    h57 = build_sql_context_from_dsn(dsn57).aggregate_strategy_hint()
    h80 = build_sql_context_from_dsn(dsn80).aggregate_strategy_hint()
    assert h57 != h80
    assert "标量子查询" in h57
    assert "CTE" in h80 or "窗口" in h80
