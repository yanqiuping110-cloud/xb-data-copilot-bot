-- 一次性迁移：将旧表名（无 copilot_ 前缀）重命名为新表名
-- 仅在本机已执行过旧版 ddl_copilot.sql 时使用；新环境请直接执行 ddl_copilot.sql
-- 执行前请备份 copilot 库

USE copilot;

RENAME TABLE sys_user TO copilot_sys_user;
RENAME TABLE sys_user_school TO copilot_sys_user_school;
RENAME TABLE ask_session TO copilot_ask_session;
RENAME TABLE ask_turn TO copilot_ask_turn;
RENAME TABLE ask_span TO copilot_ask_span;
RENAME TABLE audit_log TO copilot_audit_log;
RENAME TABLE metric_definition TO copilot_metric_definition;
RENAME TABLE sql_example TO copilot_sql_example;
