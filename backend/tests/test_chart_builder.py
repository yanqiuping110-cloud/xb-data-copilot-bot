"""chart_builder 规则引擎单测。"""

from app.agent.chart_builder import build_chart_spec, infer_visualization_from_question


def test_line_chart_time_series():
    cols = ["日期", "参与人数"]
    rows = [["2026-06-01", 10], ["2026-06-02", 20], ["2026-06-03", 15]]
    intent = infer_visualization_from_question("最近7天每日参与人数趋势")
    spec = build_chart_spec(columns=cols, rows=rows, visualization_intent=intent)
    assert spec.status == "ready"
    assert spec.chart_type in ("line", "area")
    assert spec.x_column == "日期"
    assert "参与人数" in spec.y_columns


def test_bar_chart_category_compare():
    cols = ["项目", "人数"]
    rows = [["跳绳", 100], ["跑步", 80], ["游泳", 60]]
    intent = infer_visualization_from_question("各运动项目参与人数对比")
    spec = build_chart_spec(columns=cols, rows=rows, visualization_intent=intent)
    assert spec.status == "ready"
    assert spec.chart_type in ("bar", "column", "pie")


def test_pie_chart_proportion():
    cols = ["类型", "占比"]
    rows = [["A", 40], ["B", 30], ["C", 20], ["D", 10]]
    intent = {"enabled": True, "preferred_types": ["pie"], "user_explicit": False}
    spec = build_chart_spec(columns=cols, rows=rows, visualization_intent=intent)
    assert spec.status == "ready"
    assert spec.chart_type == "pie"


def test_single_value_rejected():
    cols = ["cnt"]
    rows = [[42]]
    spec = build_chart_spec(columns=cols, rows=rows, visualization_intent={"enabled": True})
    assert spec.status == "rejected"


def test_empty_rows_rejected():
    spec = build_chart_spec(columns=["a"], rows=[], visualization_intent={"enabled": True})
    assert spec.status == "rejected"


def test_detail_question_skipped():
    intent = infer_visualization_from_question("给我明细列表")
    assert intent["enabled"] is False
    spec = build_chart_spec(
        columns=["id", "name"],
        rows=[[1, "a"], [2, "b"]],
        visualization_intent=intent,
    )
    assert spec.status == "skipped"


def test_wide_table_join_by_date_line():
    cols = ["日期", "活动A_人数", "活动B_人数"]
    rows = [
        ["2026-06-01", 10, 12],
        ["2026-06-02", 11, 13],
        ["2026-06-03", 9, 14],
    ]
    spec = build_chart_spec(
        columns=cols,
        rows=rows,
        visualization_intent={"enabled": True, "preferred_types": ["line"]},
        assembly_mode="join_by_date",
    )
    assert spec.status == "ready"
    assert spec.chart_type == "line"
    assert len(spec.y_columns) == 2
