-- V004：元数据知识库（表/字段/关系/取值）+ 指标字段关联 + 指标扩展字段
-- 执行：在 copilot 库手工运行（见 docs/DATABASE_CHANGE_POLICY.md）

-- ---------- 业务表元数据（问数白名单权威来源）----------
CREATE TABLE IF NOT EXISTS copilot_table_meta (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    table_name VARCHAR(128) NOT NULL COMMENT '业务表名',
    table_role VARCHAR(32) NULL COMMENT 'fact/dim/bridge',
    biz_domain VARCHAR(64) NULL COMMENT '业务域：活动参与/打卡/学校等',
    table_comment_auto TEXT NULL COMMENT '自动：业务库 TABLE_COMMENT',
    description_manual TEXT NULL COMMENT '人工：问数表定义，非空时优先于 auto',
    grain VARCHAR(256) NULL COMMENT '数据粒度说明',
    sch_id_column VARCHAR(64) NOT NULL DEFAULT 'sch_id' COMMENT '学校隔离字段名',
    last_introspected_at DATETIME NULL COMMENT '最近一次从业务库拉取结构时间',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用问数 0 停用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    UNIQUE KEY uk_table_name (table_name),
    KEY idx_status_deleted (status, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问数业务表元数据';

-- ---------- 字段元数据 ----------
CREATE TABLE IF NOT EXISTS copilot_column_meta (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    table_id BIGINT NOT NULL COMMENT '所属 copilot_table_meta.id',
    column_name VARCHAR(128) NOT NULL COMMENT '字段名',
    ordinal_position INT NOT NULL DEFAULT 0 COMMENT '字段顺序',
    data_type VARCHAR(64) NULL COMMENT '自动：COLUMN_TYPE',
    column_comment_auto TEXT NULL COMMENT '自动：COLUMN_COMMENT',
    description_manual TEXT NULL COMMENT '人工：问数字段定义，非空时优先于 auto',
    column_role VARCHAR(32) NULL COMMENT 'pk/fk/measure/dimension/filter/time',
    alias_json TEXT NULL COMMENT '别名 JSON 数组',
    sample_values_json TEXT NULL COMMENT '示例值 JSON',
    is_nullable TINYINT NOT NULL DEFAULT 1 COMMENT '1 可空 0 非空',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 有效 0 业务库已不存在',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    UNIQUE KEY uk_table_column (table_id, column_name),
    KEY idx_table_id (table_id, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问数字段元数据';

-- ---------- 表间关系（JOIN 提示）----------
CREATE TABLE IF NOT EXISTS copilot_table_relation (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    from_table_id BIGINT NOT NULL COMMENT '源表 id',
    from_column VARCHAR(128) NOT NULL COMMENT '源列',
    to_table_id BIGINT NOT NULL COMMENT '目标表 id',
    to_column VARCHAR(128) NOT NULL COMMENT '目标列',
    relation_type VARCHAR(32) NOT NULL DEFAULT 'logical_join' COMMENT 'fk/logical_join/lookup',
    join_hint TEXT NULL COMMENT 'JOIN 自然语言说明',
    cardinality VARCHAR(16) NULL COMMENT 'n:1/1:n/n:n',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_from_table (from_table_id, deleted),
    KEY idx_to_table (to_table_id, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问数表间关系';

-- ---------- 字段取值（枚举/全文召回）----------
CREATE TABLE IF NOT EXISTS copilot_field_value (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    column_id BIGINT NOT NULL COMMENT 'copilot_column_meta.id',
    value_text VARCHAR(512) NOT NULL COMMENT '库中实际值',
    display_label VARCHAR(256) NULL COMMENT '展示名',
    alias_json TEXT NULL COMMENT '别名 JSON 数组',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_column_value (column_id, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='字段取值/枚举';

-- ---------- 指标 ↔ 字段关联 ----------
CREATE TABLE IF NOT EXISTS copilot_metric_column (
    metric_id BIGINT NOT NULL COMMENT 'copilot_metric_definition.id',
    column_id BIGINT NOT NULL COMMENT 'copilot_column_meta.id',
    usage_type VARCHAR(32) NOT NULL DEFAULT 'measure' COMMENT 'measure/filter/group_by/join_key',
    PRIMARY KEY (metric_id, column_id, usage_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指标与字段关联';

-- ---------- 扩展已有指标表（列已存在则跳过需手工处理）----------
ALTER TABLE copilot_metric_definition
    ADD COLUMN formula_text TEXT NULL COMMENT '口径公式' AFTER description,
    ADD COLUMN filter_hint TEXT NULL COMMENT '默认过滤说明' AFTER formula_text,
    ADD COLUMN time_column VARCHAR(64) NULL COMMENT '默认时间字段' AFTER filter_hint,
    ADD COLUMN agg_type VARCHAR(32) NULL COMMENT '聚合类型' AFTER time_column,
    ADD COLUMN unit VARCHAR(32) NULL COMMENT '单位' AFTER agg_type,
    ADD COLUMN admin_only TINYINT NOT NULL DEFAULT 0 COMMENT '仅超管/运营' AFTER unit;
