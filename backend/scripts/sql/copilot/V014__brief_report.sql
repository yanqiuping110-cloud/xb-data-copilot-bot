-- V014: 问数 · 报告分析（Brief Report）
CREATE TABLE IF NOT EXISTS copilot_brief_report (
    report_id       VARCHAR(64)  NOT NULL PRIMARY KEY,
    user_id         BIGINT       NOT NULL,
    session_id      VARCHAR(64)  NOT NULL,
    trace_ids_json  TEXT         NOT NULL,
    user_prompt     TEXT         NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    pdf_path        VARCHAR(512) NULL,
    doc_json        MEDIUMTEXT   NULL,
    pdf_page_count  INT          NULL,
    pdf_file_size   INT          NULL,
    error_code      VARCHAR(64)  NULL,
    error_message   VARCHAR(512) NULL,
    deleted         TINYINT      NOT NULL DEFAULT 0,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_brief_report_user (user_id, created_at),
    INDEX idx_brief_report_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
