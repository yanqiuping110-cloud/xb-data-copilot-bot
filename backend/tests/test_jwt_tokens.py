"""JWT 签发与解析单元测试。"""

from app.auth import jwt_tokens
from app.core.context import UserRole


def test_jwt_roundtrip():
    """学校 token 应包含校维度字段。"""
    token, expires_in = jwt_tokens.create_access_token(
        user_id=42,
        role=UserRole.SCHOOL,
        secret="test-secret-key-at-least-32-chars-long",
        expire_hours=24,
        active_sch_id=1140,
        bound_sch_ids=[1140, 1220],
    )
    assert expires_in == 86400
    payload = jwt_tokens.decode_access_token(token, "test-secret-key-at-least-32-chars-long")
    assert payload["sub"] == "42"
    assert payload["role"] == "SCHOOL"
    assert payload["active_sch_id"] == 1140
    assert payload["bound_sch_ids"] == [1140, 1220]


def test_admin_token_no_school_fields():
    """运营/超管 token 不含 sch 字段，降低篡改面。"""
    token, _ = jwt_tokens.create_access_token(
        user_id=1,
        role=UserRole.ADMIN,
        secret="test-secret-key-at-least-32-chars-long",
        expire_hours=1,
    )
    payload = jwt_tokens.decode_access_token(token, "test-secret-key-at-least-32-chars-long")
    assert "active_sch_id" not in payload
    assert "bound_sch_ids" not in payload
