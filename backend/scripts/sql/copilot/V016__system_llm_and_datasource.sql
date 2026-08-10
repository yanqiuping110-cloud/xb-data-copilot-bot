-- V016：AI 模型配置 + 业务数据源配置（管理台可改，env 作冷启动种子与回退）
-- 执行：在 copilot 库手工运行（见 docs/DATABASE_CHANGE_POLICY.md、docs/LLM_DATASOURCE_CONFIG_PLAN.md）

CREATE TABLE IF NOT EXISTS copilot_llm_model (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    name VARCHAR(128) NOT NULL COMMENT '展示名',
    provider VARCHAR(64) NOT NULL DEFAULT 'openai_compatible' COMMENT '供应商标识',
    api_base VARCHAR(512) NOT NULL COMMENT 'OpenAI 兼容 API Base',
    api_key_enc TEXT NULL COMMENT 'API Key（Fernet 密文）',
    model_name VARCHAR(128) NOT NULL COMMENT '模型名',
    role VARCHAR(32) NOT NULL COMMENT 'chat | embedding',
    timeout_sec INT NOT NULL DEFAULT 120 COMMENT '超时秒',
    temperature DOUBLE NOT NULL DEFAULT 0 COMMENT '温度（embedding 可忽略）',
    extra_json TEXT NULL COMMENT '扩展 JSON：thinking、reasoning_effort、embedding_dims 等',
    is_default TINYINT NOT NULL DEFAULT 0 COMMENT '同 role 仅一条为 1',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用 0 停用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_llm_role_default (role, is_default, deleted, status),
    KEY idx_llm_deleted (deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统 AI 模型配置';

CREATE TABLE IF NOT EXISTS copilot_business_datasource (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    name VARCHAR(128) NOT NULL COMMENT '展示名',
    db_type VARCHAR(32) NOT NULL DEFAULT 'mysql' COMMENT '一期仅 mysql',
    host VARCHAR(256) NOT NULL COMMENT '主机',
    port INT NOT NULL DEFAULT 3306 COMMENT '端口',
    database_name VARCHAR(128) NOT NULL COMMENT '库名',
    username VARCHAR(128) NOT NULL COMMENT '用户名',
    password_enc TEXT NULL COMMENT '密码（Fernet 密文）',
    is_default TINYINT NOT NULL DEFAULT 0 COMMENT '全局仅一条默认问数库',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用 0 停用',
    last_test_at DATETIME NULL COMMENT '最近连通性测试时间',
    last_test_ok TINYINT NULL COMMENT '最近测试是否成功',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_ds_default (is_default, deleted, status),
    KEY idx_ds_deleted (deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务只读数据源配置';

-- ---------- 初始数据（来自当前 .env.development 生效配置；api_key_enc / password_enc 为 Fernet，依赖现网 JWT_SECRET）----------
-- 幂等：表中尚无未删除记录时才插入。更换 JWT_SECRET 后须在管理台重填 Key/密码。

INSERT INTO copilot_llm_model (
    name, provider, api_base, api_key_enc, model_name, role,
    timeout_sec, temperature, extra_json, is_default, status
)
SELECT
    'DeepSeek Chat（当前）',
    'openai_compatible',
    'https://api.deepseek.com',
    'REDACTED_FERNET_SECRET',
    'deepseek-v4-flash',
    'chat',
    120,
    0,
    '{"thinking_enabled": true, "reasoning_effort": "high"}',
    1,
    1
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM copilot_llm_model WHERE deleted = 0 AND role = 'chat' LIMIT 1
);

INSERT INTO copilot_llm_model (
    name, provider, api_base, api_key_enc, model_name, role,
    timeout_sec, temperature, extra_json, is_default, status
)
SELECT
    'Ollama Embedding（当前）',
    'openai_compatible',
    'http://127.0.0.1:11434/v1',
    'REDACTED_FERNET_SECRET',
    'qwen3-embedding:4b',
    'embedding',
    120,
    0,
    '{"embedding_dims": 2560}',
    1,
    1
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM copilot_llm_model WHERE deleted = 0 AND role = 'embedding' LIMIT 1
);

INSERT INTO copilot_business_datasource (
    name, db_type, host, port, database_name, username, password_enc,
    is_default, status
)
SELECT
    'stugrow_sport（当前）',
    'mysql',
    'REDACTED_HOST',
    18306,
    'stugrow_sport',
    'REDACTED_USER',
    'REDACTED_FERNET_SECRET',
    1,
    1
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM copilot_business_datasource WHERE deleted = 0 LIMIT 1
);
