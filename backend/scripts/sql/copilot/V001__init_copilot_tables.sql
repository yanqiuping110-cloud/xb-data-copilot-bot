-- V001：问数库初始表结构（copilot_*）
-- 执行前：将 USE copilot 改为实际库名（如 study_demo）
-- 执行方式：人工在 MYSQL_COPILOT_DATABASE 执行，禁止应用运行时 DDL
-- 回滚：无（初版）；新环境直接执行本文件

USE copilot;

-- ---------- 用户与权限 ----------
CREATE TABLE IF NOT EXISTS copilot_sys_user (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    username VARCHAR(64) NOT NULL COMMENT '登录名，全局唯一',
    password_hash VARCHAR(255) NOT NULL COMMENT 'bcrypt 密码哈希，禁止存明文',
    display_name VARCHAR(128) NULL COMMENT '显示名称',
    role ENUM('ADMIN', 'OPERATOR', 'SCHOOL') NOT NULL COMMENT '角色：超管/运营/学校',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1 启用，0 禁用',
    created_by BIGINT NULL COMMENT '创建人 copilot_sys_user.id，超管种子为 NULL',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问数系统登录账户';

CREATE TABLE IF NOT EXISTS copilot_sys_user_school (
    user_id BIGINT NOT NULL COMMENT '用户 ID，FK copilot_sys_user.id',
    sch_id INT NOT NULL COMMENT '学校 ID，对应业务库学校主键',
    sch_name VARCHAR(128) NULL COMMENT '学校名称（展示用，非权限依据）',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    PRIMARY KEY (user_id, sch_id),
    CONSTRAINT fk_copilot_user_school_user FOREIGN KEY (user_id) REFERENCES copilot_sys_user (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学校账户与学校多对多绑定';

-- ---------- 可观测：会话与提问 ----------
CREATE TABLE IF NOT EXISTS copilot_ask_session (
    session_id VARCHAR(64) PRIMARY KEY COMMENT '会话 ID（前端或客户端生成）',
    user_id BIGINT NOT NULL COMMENT '用户 ID',
    role VARCHAR(32) NOT NULL COMMENT '提问时角色快照',
    active_sch_id INT NULL COMMENT '提问时当前校 ID（学校账户）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '会话创建时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    KEY idx_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问数会话（多轮对话分组）';

CREATE TABLE IF NOT EXISTS copilot_ask_turn (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    trace_id VARCHAR(64) NOT NULL COMMENT '全链路追踪 ID，全局唯一',
    session_id VARCHAR(64) NULL COMMENT '所属会话 ID',
    user_id BIGINT NOT NULL COMMENT '用户 ID',
    role VARCHAR(32) NOT NULL COMMENT '提问时角色快照',
    active_sch_id INT NULL COMMENT '提问时当前校 ID',
    question TEXT NOT NULL COMMENT '用户自然语言问题',
    final_sql TEXT NULL COMMENT '最终执行或展示的 SQL',
    status VARCHAR(32) NOT NULL COMMENT '结果：success|fail|timeout|degraded',
    degrade_level TINYINT NOT NULL DEFAULT 0 COMMENT '降级级别：0 无，1 L1 样例，2 L2…',
    retry_count INT NOT NULL DEFAULT 0 COMMENT '重试次数',
    error_code VARCHAR(64) NULL COMMENT '失败错误码',
    latency_ms_total INT NULL COMMENT '端到端耗时（毫秒）',
    latency_ms_first_token INT NULL COMMENT '首 token 耗时（流式时）',
    latency_ms_sql_gen INT NULL COMMENT 'SQL 生成耗时',
    latency_ms_sql_exec INT NULL COMMENT 'SQL 执行耗时',
    row_count INT NULL COMMENT '结果行数',
    token_in INT NULL COMMENT 'LLM 输入 token 数',
    token_out INT NULL COMMENT 'LLM 输出 token 数',
    user_feedback VARCHAR(16) NULL COMMENT '用户反馈：up|down 等',
    is_badcase TINYINT NOT NULL DEFAULT 0 COMMENT '是否标记为 badcase：0 否，1 是',
    human_corrected_sql TEXT NULL COMMENT '人工修正后的 SQL',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提问时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    UNIQUE KEY uk_trace (trace_id),
    KEY idx_user_created (user_id, created_at),
    KEY idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='单次问数记录（核心可观测表）';

CREATE TABLE IF NOT EXISTS copilot_ask_span (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    trace_id VARCHAR(64) NOT NULL COMMENT '关联 copilot_ask_turn.trace_id',
    node_name VARCHAR(64) NOT NULL COMMENT 'LangGraph 节点名',
    started_at DATETIME(3) NOT NULL COMMENT '节点开始时间',
    duration_ms INT NOT NULL COMMENT '节点耗时（毫秒）',
    status VARCHAR(32) NOT NULL COMMENT '节点状态：success|fail 等',
    detail_json TEXT NULL COMMENT '节点详情 JSON',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    KEY idx_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问数流水线节点 Span';

CREATE TABLE IF NOT EXISTS copilot_audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    trace_id VARCHAR(64) NOT NULL COMMENT '关联 trace_id',
    user_id BIGINT NOT NULL COMMENT '用户 ID',
    role VARCHAR(32) NOT NULL COMMENT '角色快照',
    active_sch_id INT NULL COMMENT '当前校 ID',
    question TEXT NOT NULL COMMENT '用户问题',
    sql_hash VARCHAR(64) NULL COMMENT '执行 SQL 的哈希（脱敏审计）',
    tables_used VARCHAR(512) NULL COMMENT '涉及业务表列表',
    row_count INT NULL COMMENT '返回行数',
    client_ip VARCHAR(64) NULL COMMENT '客户端 IP',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '审计时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    KEY idx_user_created (user_id, created_at),
    KEY idx_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问数合规审计日志';

-- ---------- 指标与样例 SQL（结构化语义层，MVP 可手填）----------
CREATE TABLE IF NOT EXISTS copilot_metric_definition (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    metric_code VARCHAR(64) NOT NULL COMMENT '指标编码，唯一',
    metric_name VARCHAR(128) NOT NULL COMMENT '指标中文名',
    description TEXT NULL COMMENT '指标说明与口径',
    sql_template TEXT NULL COMMENT 'SQL 模板或参考 SQL',
    relevant_tables VARCHAR(512) NULL COMMENT '相关业务表，逗号分隔',
    alias_json TEXT NULL COMMENT '别名 JSON 数组，用于问句匹配',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1 启用，0 停用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    UNIQUE KEY uk_metric_code (metric_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指标定义（结构化语义层）';

CREATE TABLE IF NOT EXISTS copilot_sql_example (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    question_pattern VARCHAR(512) NOT NULL COMMENT '问题模式或示例问句',
    sql_text TEXT NOT NULL COMMENT '对应 SQL',
    meta_json TEXT NULL COMMENT 'JSON：answerTemplate、matchAll、matchAny、adminOnly 等',
    role_scope VARCHAR(32) NULL COMMENT '适用角色，NULL 表示全部',
    degrade_priority INT NOT NULL DEFAULT 100 COMMENT 'L1 降级优先级，越小越优先',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    KEY idx_role (role_scope)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='样例 SQL（L1 降级匹配）';
