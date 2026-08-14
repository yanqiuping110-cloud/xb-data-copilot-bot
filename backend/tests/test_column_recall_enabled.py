"""字段 recall_enabled 序列化与问数可见性单测。"""

from app.meta.repository import ColumnMetaRow
from app.meta.service import column_to_dict


def _col(*, status: int = 1, recall_enabled: int = 1) -> ColumnMetaRow:
    return ColumnMetaRow(
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
        status=status,
        recall_enabled=recall_enabled,
    )


def test_column_to_dict_exposes_recall_enabled():
    row = _col(recall_enabled=0)
    data = column_to_dict(row)
    assert data["recallEnabled"] is False
    assert data["status"] == 1


def test_is_ask_visible_requires_status_and_recall_enabled():
    assert _col(status=1, recall_enabled=1).is_ask_visible is True
    assert _col(status=1, recall_enabled=0).is_ask_visible is False
    assert _col(status=0, recall_enabled=1).is_ask_visible is False
