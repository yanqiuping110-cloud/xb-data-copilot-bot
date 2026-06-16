-- V010：动态数据权限（DataScope · 第 13 周）
-- 执行：在 copilot 库手工运行

CREATE TABLE IF NOT EXISTS copilot_scope_dimension (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    code VARCHAR(64) NOT NULL COMMENT '维度唯一标识，如 school、region',
    display_name VARCHAR(128) NOT NULL COMMENT '展示名',
    value_type VARCHAR(16) NOT NULL DEFAULT 'int' COMMENT 'int/string',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用 0 停用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    UNIQUE KEY uk_code (code),
    KEY idx_status_deleted (status, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据范围维度注册';

CREATE TABLE IF NOT EXISTS copilot_table_scope_binding (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    table_id BIGINT NOT NULL COMMENT 'FK copilot_table_meta.id',
    dimension_code VARCHAR(64) NOT NULL COMMENT 'FK copilot_scope_dimension.code',
    column_name VARCHAR(128) NOT NULL COMMENT '该表上用于过滤的物理列名',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_table_dim (table_id, dimension_code, deleted),
    KEY idx_dimension (dimension_code, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='表与范围维度列绑定';

CREATE TABLE IF NOT EXISTS copilot_user_data_grant (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    user_id BIGINT NOT NULL COMMENT 'copilot_sys_user.id',
    dimension_code VARCHAR(64) NOT NULL COMMENT '范围维度 code',
    operator VARCHAR(16) NOT NULL DEFAULT 'in' COMMENT 'in/all',
    values_json TEXT NOT NULL COMMENT '允许的值列表 JSON',
    created_by BIGINT NULL COMMENT '授权操作人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_user_dim (user_id, dimension_code, deleted),
    KEY idx_user (user_id, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户行级数据授权';

CREATE TABLE IF NOT EXISTS copilot_user_table_grant (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    user_id BIGINT NOT NULL COMMENT 'copilot_sys_user.id',
    table_name VARCHAR(128) NOT NULL COMMENT '允许查询的表名',
    effect VARCHAR(16) NOT NULL DEFAULT 'allow' COMMENT 'allow',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_user_table (user_id, table_name, deleted),
    KEY idx_user (user_id, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表级授权';

CREATE TABLE IF NOT EXISTS copilot_column_deny (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    user_id BIGINT NULL COMMENT 'NULL=全局敏感列',
    table_name VARCHAR(128) NOT NULL COMMENT '表名',
    column_name VARCHAR(128) NOT NULL COMMENT '列名',
    reason VARCHAR(256) NULL COMMENT '审计说明',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    KEY idx_table_col (table_name, column_name, deleted),
    KEY idx_user (user_id, deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='列 deny-list';

-- 种子：school 维度（列名由 table_scope_binding 配置，不在此写死业务列）
INSERT INTO copilot_scope_dimension (code, display_name, value_type, status)
SELECT 'school', '学校', 'int', 1
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM copilot_scope_dimension WHERE code = 'school' AND deleted = 0
);
