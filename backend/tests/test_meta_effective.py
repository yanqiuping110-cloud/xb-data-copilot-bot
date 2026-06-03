"""元数据 effective 描述与表名校验单测。"""

import pytest

from app.meta.effective import effective_description
from app.meta.exceptions import MetaError
from app.meta.introspector import validate_table_name


def test_effective_prefers_manual():
    assert effective_description("人工定义", "自动备注") == "人工定义"


def test_effective_falls_back_to_auto():
    assert effective_description(None, "自动备注") == "自动备注"
    assert effective_description("", "自动备注") == "自动备注"
    assert effective_description("  ", "自动备注") == "自动备注"


def test_effective_none_when_both_empty():
    assert effective_description(None, None) is None
    assert effective_description("", "") is None


def test_validate_table_name_ok():
    assert validate_table_name("sport_activity_qzs_record") == "sport_activity_qzs_record"


@pytest.mark.parametrize("bad", ["", "a-b", "a;b", "select *"])
def test_validate_table_name_rejects(bad):
    with pytest.raises(MetaError) as exc:
        validate_table_name(bad)
    assert exc.value.code == "INVALID_TABLE_NAME"
