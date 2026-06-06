-- V005：字段「参与召回」开关（运营标注废弃字段，与 status=业务库是否存在 解耦）
-- 执行：在 copilot 库手工运行（见 docs/DATABASE_CHANGE_POLICY.md）

ALTER TABLE copilot_column_meta
    ADD COLUMN recall_enabled TINYINT NOT NULL DEFAULT 1
        COMMENT '1 参与混合召回/ES索引 0 废弃不参与'
    AFTER status;
