-- V010：指标字段关联表支持逻辑删除（replace 时不再物理 DELETE）

USE copilot;

ALTER TABLE copilot_metric_column
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除' AFTER usage_type;

ALTER TABLE copilot_metric_column
    ADD KEY idx_metric_deleted (metric_id, deleted);
