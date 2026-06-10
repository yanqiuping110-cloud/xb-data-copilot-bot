-- 问数 turn 结果快照（供对话历史 UI 回放）
USE copilot;

ALTER TABLE copilot_ask_turn
    ADD COLUMN result_json LONGTEXT NULL
        COMMENT '问数结果快照 JSON：answer/columns/rows/error_message'
        AFTER trace_log;
