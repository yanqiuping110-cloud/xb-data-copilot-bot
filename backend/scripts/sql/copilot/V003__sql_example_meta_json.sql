-- 样例 SQL 扩展元数据（回答模板、匹配规则等），供 L1 动态配置
ALTER TABLE copilot_sql_example
    ADD COLUMN meta_json TEXT NULL COMMENT 'JSON：answerTemplate、matchAll、matchAny、adminOnly 等' AFTER sql_text;
