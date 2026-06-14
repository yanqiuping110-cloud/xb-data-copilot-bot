/**
 * 报表 Service 解析 fixture
 */
package com.sport.report;

import org.springframework.stereotype.Service;

/**
 * 活动参与统计业务逻辑
 */
@Service
public class ActivityReportService {

    /**
     * 按学校统计参与人数
     */
    public int countParticipantsBySchool(Long schId) {
        return 0;
    }

    /**
     * 各年级项目交叉汇总
     */
    public Object buildGradeProjectPivot(Long schId) {
        return null;
    }
}
