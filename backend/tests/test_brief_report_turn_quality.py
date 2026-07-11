"""问数轮次质量判定单测。"""

from app.brief_report.turn_quality import is_empty_answer, turn_has_reportable_content


def test_empty_answer_detected():
    assert is_empty_answer("根据查询结果，共返回 0 行数据。")
    assert not is_empty_answer("3月参与人数达1200人。")


def test_turn_without_data_not_reportable():
    turn = {
        "status": "success",
        "row_count": 0,
        "rows": [],
        "chart_spec": None,
        "answer": "根据查询结果，共返回 0 行数据。",
    }
    assert not turn_has_reportable_content(turn)


def test_turn_with_rows_reportable():
    turn = {
        "status": "success",
        "row_count": 5,
        "rows": [[1]],
        "answer": "共5个月数据。",
    }
    assert turn_has_reportable_content(turn)
