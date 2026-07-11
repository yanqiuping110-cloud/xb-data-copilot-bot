-- L1 样例：新增详细描述字段（问句模式 + SQL + 描述 三要素）
ALTER TABLE copilot_sql_example
    ADD COLUMN description TEXT NULL COMMENT 'L1样例详细描述（业务口径/适用场景）' AFTER sql_text;
