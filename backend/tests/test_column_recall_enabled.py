"""字段 recall_enabled 序列化单测。"""

from app.meta.repository import ColumnMetaRow
from app.meta.service import column_to_dict


def test_column_to_dict_exposes_recall_enabled():
    row = ColumnMetaRow(
        id=1,
        table_id=10,
        column_name="legacy_flag",
        ordinal_position=1,
        data_type="int(11)",
        column_comment_auto="旧字段",
        description_manual=None,
        column_role=None,
        alias_json=None,
        is_nullable=1,
        status=1,
        recall_enabled=0,
    )
    data = column_to_dict(row)
    assert data["recallEnabled"] is False
    assert data["status"] == 1
