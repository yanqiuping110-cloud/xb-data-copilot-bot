-- V018：系统参数（仅超管可改；问数 SQL 默认 LIMIT 等）
-- 执行：在 copilot 库手工运行（见 docs/90-DATABASE_CHANGE_POLICY.md）

CREATE TABLE IF NOT EXISTS copilot_sys_param (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    param_key VARCHAR(64) NOT NULL COMMENT '参数键，如 sql_max_rows',
    param_value VARCHAR(512) NOT NULL COMMENT '参数值（字符串存储）',
    value_type VARCHAR(16) NOT NULL DEFAULT 'int' COMMENT 'int | string | bool',
    display_name VARCHAR(128) NOT NULL COMMENT '展示名',
    description VARCHAR(512) NULL COMMENT '说明',
    min_value INT NULL COMMENT '数值下限（可选）',
    max_value INT NULL COMMENT '数值上限（可选）',
    updated_by BIGINT NULL COMMENT '最后修改人 copilot_sys_user.id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    UNIQUE KEY uk_sys_param_key (param_key),
    KEY idx_sys_param_deleted (deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统参数（仅超管可改）';

INSERT INTO copilot_sys_param (
    param_key, param_value, value_type, display_name, description, min_value, max_value
)
SELECT
    'sql_max_rows',
    '100',
    'int',
    '问数 SQL 默认 LIMIT',
    '查询执行时强制附加的最大行数；模型写出更大 LIMIT 也会被压到此值。',
    1,
    10000
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM copilot_sys_param WHERE param_key = 'sql_max_rows' AND deleted = 0 LIMIT 1
);
