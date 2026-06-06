-- 问数 turn 全链路 trace 日志
USE copilot;

ALTER TABLE copilot_ask_turn
    ADD COLUMN trace_log LONGTEXT NULL
        COMMENT '问数全链路 trace JSON：节点顺序、耗时、摘要、异常'
        AFTER human_corrected_sql;
