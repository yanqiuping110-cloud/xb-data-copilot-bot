-- Phase 2 · 术语库 + L1 审核发布工作流
USE copilot;

CREATE TABLE IF NOT EXISTS copilot_glossary_term (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    term VARCHAR(128) NOT NULL COMMENT '业务术语/别名',
    canonical_name VARCHAR(256) NOT NULL COMMENT '标准指标或字段表述',
    definition TEXT NULL COMMENT '口径说明',
    ref_type ENUM('metric','column','table','concept') NOT NULL DEFAULT 'concept' COMMENT '引用类型',
    ref_id BIGINT NULL COMMENT '关联 copilot_metric_definition.id 等',
    scope_role VARCHAR(32) NULL COMMENT 'ADMIN/OPERATOR/SCHOOL，空=全局',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '0草稿 1已发布 2停用',
    created_by BIGINT NULL COMMENT '创建人 user_id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (id),
    KEY idx_glossary_status (status, deleted),
    KEY idx_glossary_term (term(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='术语库';

-- copilot_sql_example 审核字段（列已存在则跳过需手工检查）
ALTER TABLE copilot_sql_example
    ADD COLUMN source_trace_id VARCHAR(64) NULL COMMENT '来自 badcase 沉淀' AFTER meta_json;
ALTER TABLE copilot_sql_example
    ADD COLUMN review_status TINYINT NOT NULL DEFAULT 1 COMMENT '0草稿 1已发布' AFTER source_trace_id;
ALTER TABLE copilot_sql_example
    ADD COLUMN reviewed_by BIGINT NULL COMMENT '审核人' AFTER review_status;
ALTER TABLE copilot_sql_example
    ADD COLUMN reviewed_at DATETIME NULL COMMENT '审核时间' AFTER reviewed_by;
