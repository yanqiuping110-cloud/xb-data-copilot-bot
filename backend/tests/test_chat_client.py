"""问数聊天对话框前端响应裁剪。"""

from app.ask.chat_client import can_show_sql_in_chat, sanitize_chat_sql
from app.core.context import UserContext, UserRole


def test_only_admin_sees_sql_in_chat():
    admin = UserContext(trace_id="t1", user_id=1, username="admin", role=UserRole.ADMIN)
    operator = UserContext(trace_id="t2", user_id=2, username="ops", role=UserRole.OPERATOR)
    school = UserContext(
        trace_id="t3",
        user_id=3,
        username="sch",
        role=UserRole.SCHOOL,
        active_sch_id=1140,
        bound_sch_ids=[1140],
    )
    sql = "SELECT 1"

    assert can_show_sql_in_chat(admin) is True
    assert can_show_sql_in_chat(operator) is False
    assert can_show_sql_in_chat(school) is False

    assert sanitize_chat_sql(admin, sql) == sql
    assert sanitize_chat_sql(operator, sql) is None
    assert sanitize_chat_sql(school, sql) is None
    assert sanitize_chat_sql(admin, None) is None
