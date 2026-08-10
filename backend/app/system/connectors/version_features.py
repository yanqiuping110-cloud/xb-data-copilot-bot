"""版本字符串解析与特性规则。"""

from __future__ import annotations

import re


def parse_version_tuple(server_version: str | None) -> tuple[int, int]:
    if not server_version:
        return (0, 0)
    m = re.search(r"(\d+)\.(\d+)", server_version)
    if not m:
        return (0, 0)
    return int(m.group(1)), int(m.group(2))


def mysql_family_features(server_version: str | None) -> frozenset[str]:
    major, minor = parse_version_tuple(server_version)
    feats = {"select", "join", "subquery", "group_by"}
    # MySQL 8.0+ / MariaDB 10.2+ 近似：窗口与 CTE
    if major > 8 or (major == 8 and minor >= 0) or major >= 10:
        feats |= {"cte", "window"}
    return frozenset(feats)


def postgres_features(server_version: str | None) -> frozenset[str]:
    feats = {"select", "join", "subquery", "group_by", "cte", "window"}
    major, _ = parse_version_tuple(server_version)
    if major >= 12:
        feats |= {"generated_columns"}
    return frozenset(feats)


def tsql_features(server_version: str | None) -> frozenset[str]:
    return frozenset({"select", "join", "subquery", "group_by", "cte", "window"})


def clickhouse_features(server_version: str | None) -> frozenset[str]:
    return frozenset({"select", "join", "subquery", "group_by", "cte", "window"})
