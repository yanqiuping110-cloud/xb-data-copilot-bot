-- V002：问数库全表增加逻辑删除字段 deleted
-- 执行前：将 USE copilot 改为实际库名（如 study_demo）
-- deleted：0 未删除，1 已删除；禁止物理 DELETE，见 docs/DATABASE_CHANGE_POLICY.md

USE copilot;

ALTER TABLE copilot_sys_user
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER updated_at;

ALTER TABLE copilot_sys_user_school
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER sch_name;

ALTER TABLE copilot_ask_session
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER created_at;

ALTER TABLE copilot_ask_turn
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER created_at;

ALTER TABLE copilot_ask_span
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER detail_json;

ALTER TABLE copilot_audit_log
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER created_at;

ALTER TABLE copilot_metric_definition
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER created_at;

ALTER TABLE copilot_sql_example
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER created_at;

-- 常用查询索引（可选，便于 WHERE deleted = 0）
ALTER TABLE copilot_sys_user ADD KEY idx_deleted (deleted);
ALTER TABLE copilot_sys_user_school ADD KEY idx_user_deleted (user_id, deleted);
ALTER TABLE copilot_ask_turn ADD KEY idx_deleted_created (deleted, created_at);
