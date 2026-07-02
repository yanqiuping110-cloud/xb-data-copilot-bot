"""Agent 上下文：字段格式化与工具观察。"""

from app.agent.agent_llm import _default_tool_args, _fallback_action
from app.agent.context_builder import (
    _format_describe_table_observation,
    _format_tool_observations,
    _pick_candidate_tables,
    _sort_observations_for_prompt,
    format_column_prompt_item,
    format_prompt_column_line,
)
from app.meta.repository import ColumnMetaRow


def _col(
    name: str,
    *,
    desc: str | None = None,
    aliases: str | None = None,
) -> ColumnMetaRow:
    return ColumnMetaRow(
        id=1,
        table_id=1,
        column_name=name,
        ordinal_position=1,
        data_type="int",
        column_comment_auto=None,
        description_manual=desc,
        column_role="metric",
        alias_json=aliases,
        is_nullable=1,
        status=1,
    )


def test_format_column_prompt_item_with_desc_and_aliases():
    col = _col("sport_time", desc="打卡时间", aliases='["打卡时间","运动时长"]')
    assert format_column_prompt_item("sport_time", col) == "sport_time(打卡时间)[打卡时间,运动时长]"


def test_format_prompt_column_line_truncates_by_char_budget():
    cols = {
        f"c{i}": _col(f"c{i}", desc="x" * 40) for i in range(20)
    }
    names = list(cols.keys())
    line = format_prompt_column_line("t", names, cols, max_chars=200)
    assert line.startswith("- t: ")
    assert "已截断" in line


def test_pick_candidate_tables_skips_java_class_names():
    tables = ["SportActivityClassPoint", "sport_activity_qzs_time", "sport_project"]
    assert _pick_candidate_tables(tables) == ["sport_activity_qzs_time", "sport_project"]


def test_sort_observations_prioritize_candidate_describe():
    obs = [
        {"tool": "describe_table", "args": {"table": "other"}, "result": {"columns": []}},
        {"tool": "describe_table", "args": {"table": "sport_activity_qzs_time"}, "result": {"columns": []}},
    ]
    ordered = _sort_observations_for_prompt(obs, ["sport_activity_qzs_time", "other"])
    assert ordered[0]["args"]["table"] == "sport_activity_qzs_time"


def test_format_describe_table_observation_includes_aliases():
    result = {
        "description": "打卡明细",
        "columns": [
            {
                "name": "sport_time",
                "data_type": "int",
                "role": "metric",
                "description": "打卡时间",
                "aliases": ["打卡时间"],
            }
        ],
    }
    lines = _format_describe_table_observation("sport_activity_qzs_time", result)
    assert any("表说明：打卡明细" in line for line in lines)
    assert any("别名[打卡时间]" in line for line in lines)


def test_format_tool_observations_describe_table_multiline():
    obs = [
        {
            "tool": "describe_table",
            "args": {"table": "sport_activity_qzs_time"},
            "result": {
                "description": "打卡",
                "columns": [{"name": "sport_time", "description": "打卡时间", "aliases": ["打卡时间"]}],
            },
        }
    ]
    lines = _format_tool_observations(obs, candidate_tables=["sport_activity_qzs_time"])
    text = "\n".join(lines)
    assert "describe_table(sport_activity_qzs_time)" in text
    assert "别名[打卡时间]" in text


def test_fallback_describe_table_retries_next_candidate():
    plan = {"steps": [{"needs_tool": ["describe_table"]}]}
    tables = ["SportActivityClassPoint", "sport_activity_qzs_time"]
    first = _fallback_action(plan, [], default_tables=tables, question="打卡时间")
    assert first["args"]["table"] == "sport_activity_qzs_time"

    retry = _fallback_action(
        plan,
        [
            {
                "tool": "describe_table",
                "args": {"table": "sport_activity_qzs_time"},
                "result": {"error": "TABLE_NOT_FOUND", "table": "sport_activity_qzs_time"},
            }
        ],
        default_tables=tables,
        question="打卡时间",
    )
    assert retry["action"] == "finish"


def test_default_tool_args_describe_picks_first_valid_candidate():
    args = _default_tool_args(
        "describe_table",
        ["SportActivityClassPoint", "sport_activity_qzs_time"],
        "q",
        [],
    )
    assert args == {"table": "sport_activity_qzs_time"}
