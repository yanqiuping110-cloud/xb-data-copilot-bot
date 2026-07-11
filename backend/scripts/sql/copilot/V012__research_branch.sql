-- 深度分析报告 · 章节分支（Phase 2）
ALTER TABLE copilot_research_report
    ADD COLUMN parent_report_id VARCHAR(32) NULL COMMENT '分支来源报告 ID' AFTER template_code,
    ADD COLUMN branch_from_section INT NULL COMMENT '从第几节开始 fork' AFTER parent_report_id;

ALTER TABLE copilot_research_report
    ADD INDEX idx_parent_report (parent_report_id);
