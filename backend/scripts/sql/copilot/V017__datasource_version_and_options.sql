-- V017: 业务数据源版本探测与扩展选项
ALTER TABLE copilot_business_datasource
  ADD COLUMN options_json TEXT NULL COMMENT 'SSL/schema/额外参数 JSON' AFTER password_enc,
  ADD COLUMN server_version VARCHAR(128) NULL COMMENT '最近探测到的数据库版本串' AFTER options_json,
  ADD COLUMN version_checked_at DATETIME NULL COMMENT '版本探测时间' AFTER server_version;
