-- V007：Agent Memory（会话扩展、用户偏好、会话摘要）
-- 执行：mysql -u copilot -p copilot < backend/scripts/sql/copilot/V007__agent_memory.sql

-- ---------- 扩展问数会话表 ----------
ALTER TABLE copilot_ask_session
    ADD COLUMN title VARCHAR(128) NULL COMMENT '对话标题，首问截取' AFTER active_sch_id,
    ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近提问时间' AFTER created_at,
    ADD COLUMN turn_count INT NOT NULL DEFAULT 0 COMMENT '成功 turn 累计' AFTER updated_at,
    ADD COLUMN context_snapshot_json JSON NULL COMMENT '首问 JWT 上下文快照（审计用，不参与 Memory 过滤）' AFTER turn_count;

ALTER TABLE copilot_ask_session
    ADD KEY idx_user_updated (user_id, updated_at);

-- ---------- 用户偏好（L2，跨会话）----------
CREATE TABLE IF NOT EXISTS copilot_user_preference (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    user_id BIGINT NOT NULL COMMENT '用户 ID',
    pref_key VARCHAR(64) NOT NULL COMMENT '偏好键（白名单）',
    pref_value JSON NOT NULL COMMENT '偏好值',
    source VARCHAR(16) NOT NULL DEFAULT 'explicit' COMMENT 'explicit|inferred（仅 explicit 进 Prompt）',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    UNIQUE KEY uk_user_key (user_id, pref_key),
    KEY idx_user_updated (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户问数偏好记忆';

-- ---------- 会话摘要（P1，多轮压缩）----------
CREATE TABLE IF NOT EXISTS copilot_session_summary (
    session_id VARCHAR(64) PRIMARY KEY COMMENT '会话 ID',
    user_id BIGINT NOT NULL COMMENT '用户 ID',
    summary_text TEXT NULL COMMENT '多轮摘要文本',
    slot_json JSON NULL COMMENT '结构化槽位快照',
    turn_count INT NOT NULL DEFAULT 0 COMMENT '已摘要轮次',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    KEY idx_user_updated (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话多轮摘要（Agent Memory P1）';
