"""
双库 SQL 安全策略（代码层强制）。

业务库 MYSQL_BUSINESS_*：
  禁止一切 DML（增删改数据）与 DDL（增删改表/字段），仅允许 SELECT。

问数库 MYSQL_COPILOT_*：
  允许 INSERT / UPDATE（用户、审计等业务数据）；
  禁止物理 DELETE，删除须 UPDATE deleted=1（0 未删除，1 已删除）；
  禁止 DDL（建表/改表/删表/改字段）——表结构变更仅能通过 scripts/sql/ 版本文件人工执行。
"""

from __future__ import annotations

import re

# DML：改数据
_FORBIDDEN_DML = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|MERGE|CALL|LOAD\s+DATA)\b",
    re.IGNORECASE,
)

# DDL：改表结构
_FORBIDDEN_DDL = re.compile(
    r"\b(CREATE|ALTER|DROP|RENAME|TRUNCATE)\b",
    re.IGNORECASE,
)

# 问数库禁止物理 DELETE（须逻辑删除 deleted=1）
_FORBIDDEN_PHYSICAL_DELETE = re.compile(r"\bDELETE\b", re.IGNORECASE)
_FORBIDDEN_PRIVILEGE = re.compile(
    r"\b(GRANT|REVOKE|SET\s+GLOBAL)\b",
    re.IGNORECASE,
)


class DatabasePolicyError(Exception):
    """数据库策略违反。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class BusinessWriteForbiddenError(DatabasePolicyError):
    """业务库禁止写操作或 DDL。"""


class CopilotDdlForbiddenError(DatabasePolicyError):
    """问数库运行时禁止 DDL。"""


class CopilotPhysicalDeleteForbiddenError(DatabasePolicyError):
    """问数库禁止物理 DELETE。"""


def _normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";")


def is_dml_statement(sql: str) -> bool:
    """是否为改数据的 DML。"""
    return bool(_FORBIDDEN_DML.search(_normalize_sql(sql)))


def is_ddl_statement(sql: str) -> bool:
    """是否为改表结构的 DDL。"""
    return bool(_FORBIDDEN_DDL.search(_normalize_sql(sql)))


def assert_business_readonly_sql(sql: str) -> None:
    """
    业务库执行前校验：仅允许 SELECT，禁止 DML / DDL / 多语句。

    与 sql_guard.validate_sql 配合使用（防御纵深）。
    """
    stripped = _normalize_sql(sql)
    if not stripped:
        raise BusinessWriteForbiddenError("EMPTY_SQL", "SQL 不能为空")
    if ";" in stripped:
        raise BusinessWriteForbiddenError("MULTI_STATEMENT", "禁止多语句执行")
    if _FORBIDDEN_DML.search(stripped):
        raise BusinessWriteForbiddenError(
            "BUSINESS_DML_FORBIDDEN",
            "业务库禁止 INSERT/UPDATE/DELETE 等写数据操作",
        )
    if _FORBIDDEN_DDL.search(stripped):
        raise BusinessWriteForbiddenError(
            "BUSINESS_DDL_FORBIDDEN",
            "业务库禁止 CREATE/ALTER/DROP 等改表操作",
        )
    if _FORBIDDEN_PRIVILEGE.search(stripped):
        raise BusinessWriteForbiddenError("BUSINESS_PRIVILEGE_FORBIDDEN", "业务库禁止权限变更语句")
    if not stripped.upper().lstrip().startswith("SELECT"):
        raise BusinessWriteForbiddenError("BUSINESS_SELECT_ONLY", "业务库仅允许 SELECT 查询")


def assert_copilot_no_ddl(sql: str) -> None:
    """问数库运行时校验：禁止任何 DDL。"""
    stripped = _normalize_sql(sql)
    if not stripped:
        return
    if is_ddl_statement(stripped):
        raise CopilotDdlForbiddenError(
            "COPILOT_DDL_FORBIDDEN",
            "问数库禁止在应用运行时执行 DDL；请使用 scripts/sql/copilot/ 版本 SQL 人工变更表结构",
        )


def assert_copilot_no_physical_delete(sql: str) -> None:
    """问数库运行时校验：禁止 DELETE，删除须 UPDATE deleted=1。"""
    stripped = _normalize_sql(sql)
    if not stripped:
        return
    if _FORBIDDEN_PHYSICAL_DELETE.search(stripped):
        raise CopilotPhysicalDeleteForbiddenError(
            "COPILOT_DELETE_FORBIDDEN",
            "问数库禁止物理 DELETE；请使用 UPDATE ... SET deleted=1 逻辑删除",
        )


def assert_copilot_runtime_sql(sql: str) -> None:
    """问数库运行时 SQL 策略：禁止 DDL + 禁止物理 DELETE。"""
    assert_copilot_no_ddl(sql)
    assert_copilot_no_physical_delete(sql)
