"""result_assembler 纯函数单测。"""

from app.agent.result_assembler import (
    assemble_intermediate_results,
    join_result_sets,
    pivot_wide,
)


def test_join_on_common_grade_column():
    left_cols = ["年级", "人数"]
    left_rows = [["一年级", 10], ["二年级", 20]]
    right_cols = ["年级", "班级数"]
    right_rows = [["一年级", 3], ["二年级", 4]]
    cols, rows = join_result_sets(left_cols, left_rows, right_cols, right_rows)
    assert cols == ["年级", "人数", "班级数"]
    assert rows == [["一年级", 10, 3], ["二年级", 20, 4]]


def test_pivot_wide_by_project():
    cols = ["年级", "项目", "人次"]
    rows = [
        ["一年级", "跳绳", 100],
        ["一年级", "跑步", 80],
        ["二年级", "跳绳", 90],
    ]
    out_cols, out_rows = pivot_wide(cols, rows, "项目")
    assert "一年级_人次" in out_cols or "跳绳_人次" in out_cols
    assert len(out_rows) == 2


def test_assemble_single_step():
    intermediate = [
        {
            "step_id": 1,
            "goal": "统计人数",
            "columns": ["cnt"],
            "rows": [[42]],
            "row_count": 1,
        }
    ]
    cols, rows, mode = assemble_intermediate_results(intermediate, None)
    assert mode == "single"
    assert cols == ["cnt"]
    assert rows == [[42]]


def test_assemble_join_two_steps():
    intermediate = [
        {
            "step_id": 1,
            "columns": ["年级", "a"],
            "rows": [["一年级", 1]],
        },
        {
            "step_id": 2,
            "columns": ["年级", "b"],
            "rows": [["一年级", 2]],
        },
    ]
    cols, rows, mode = assemble_intermediate_results(intermediate, {"steps": []})
    assert mode == "join"
    assert "a" in cols and "b" in cols
    assert rows == [["一年级", 1, 2]]


def test_assemble_compare_by_date_with_labels():
    from app.agent.result_assembler import assemble_compare_by_date

    step_a = {
        "step_id": 1,
        "entity_label": "活动A",
        "columns": ["date", "check_in_count", "sport_count"],
        "rows": [["2026-05-20", 10, 100], ["2026-05-21", 12, 110]],
    }
    step_b = {
        "step_id": 2,
        "entity_label": "活动B",
        "columns": ["date", "check_in_count", "sport_count"],
        "rows": [["2026-05-20", 5, 50], ["2026-05-21", 6, 55]],
    }
    cols, rows = assemble_compare_by_date([step_a, step_b], join_key="date")
    assert "date" in cols
    assert any("活动A" in c for c in cols)
    assert any("活动B" in c for c in cols)
    assert len(rows) == 2


def test_assemble_compare_by_date_chinese_join_key_compat():
    """旧 plan join_key=日期 仍可对齐英文 date 列。"""
    from app.agent.result_assembler import assemble_compare_by_date

    step_a = {
        "step_id": 1,
        "entity_label": "A",
        "columns": ["date", "cnt"],
        "rows": [["2026-01-01", 1]],
    }
    step_b = {
        "step_id": 2,
        "entity_label": "B",
        "columns": ["date", "cnt"],
        "rows": [["2026-01-01", 2]],
    }
    cols, rows = assemble_compare_by_date([step_a, step_b], join_key="日期")
    assert "date" in cols
    assert len(rows) == 1
