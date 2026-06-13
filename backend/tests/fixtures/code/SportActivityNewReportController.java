/**
 * 活动报表 Controller 解析 fixture（第 10 周单测）
 */
package com.sport.report;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 学校活动参与报表：按项目统计参与人数
 */
@RestController
@RequestMapping("/api/report/activity")
public class SportActivityNewReportController {

    /**
     * 按学校查询活动参与汇总
     */
    @GetMapping("/listBySchool")
    public Object listBySchool() {
        return null;
    }

    /**
     * 各年级各项目参与人数交叉表
     */
    @GetMapping("/gradeProjectPivot")
    public Object gradeProjectPivot() {
        return null;
    }
}
