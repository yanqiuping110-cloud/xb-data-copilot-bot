"""
运营账户访问超管 API 应返回 403。

使用依赖覆盖注入 OPERATOR 上下文，无需真实 MySQL。
"""

import pytest
from fastapi.testclient import TestClient

from app.core.context import UserContext, UserRole
from app.core.security import get_current_user
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    ops_ctx = UserContext(
        trace_id="t-ops",
        user_id=2,
        username="ops01",
        role=UserRole.OPERATOR,
    )

    async def _ops_user():
        return ops_ctx

    app.dependency_overrides[get_current_user] = _ops_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_operator_list_users_forbidden(client):
    """require_admin 应拦截非 ADMIN。"""
    resp = client.get("/api/v1/admin/users", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
