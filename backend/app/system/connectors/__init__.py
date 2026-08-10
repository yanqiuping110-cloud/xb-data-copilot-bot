"""启动时注册已安装驱动对应的连接器。"""

from __future__ import annotations

from app.system.connectors import registry
from app.system.connectors.mysql import doris_connector, mysql_connector, starrocks_connector


def bootstrap_connectors() -> None:
    """幂等注册。MySQL 族始终可用；其它引擎按已装驱动注册。"""
    registry.register(mysql_connector())
    registry.register(doris_connector())
    registry.register(starrocks_connector())

    try:
        import asyncpg  # noqa: F401

        from app.system.connectors.postgresql import PostgresqlConnector

        registry.register(PostgresqlConnector())
    except ImportError:
        registry.mark_unavailable(
            "postgresql",
            "未安装 asyncpg，请 pip install asyncpg",
        )

    # SQL Server：aioodbc 或 pymssql 任一即可
    try:
        import aioodbc  # noqa: F401

        has_mssql = True
    except ImportError:
        try:
            import pymssql  # noqa: F401

            has_mssql = True
        except ImportError:
            has_mssql = False
    if has_mssql:
        from app.system.connectors.sqlserver import SqlServerConnector

        registry.register(SqlServerConnector())
    else:
        registry.mark_unavailable(
            "sqlserver",
            "未安装 aioodbc 或 pymssql",
        )

    # ClickHouse：asynch 或 clickhouse-connect
    try:
        import asynch  # noqa: F401

        has_ch = True
    except ImportError:
        try:
            import clickhouse_connect  # noqa: F401

            has_ch = True
        except ImportError:
            has_ch = False
    if has_ch:
        from app.system.connectors.clickhouse import ClickhouseConnector

        registry.register(ClickhouseConnector())
    else:
        registry.mark_unavailable(
            "clickhouse",
            "未安装 clickhouse-connect 或 asynch",
        )

    try:
        import oracledb  # noqa: F401

        from app.system.connectors.oracle import OracleConnector

        registry.register(OracleConnector())
    except ImportError:
        registry.mark_unavailable("oracle", "未安装 oracledb")

    try:
        import aiosqlite  # noqa: F401
        import pandas  # noqa: F401

        from app.system.connectors.excel import ExcelCsvConnector

        registry.register(ExcelCsvConnector())
    except ImportError:
        registry.mark_unavailable(
            "excel",
            "未安装 aiosqlite/pandas（Excel/CSV 需要）",
        )


bootstrap_connectors()
