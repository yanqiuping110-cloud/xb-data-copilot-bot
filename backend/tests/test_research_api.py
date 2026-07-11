"""Research API 单测（依赖覆盖，无需 MySQL）。"""

import pytest
from fastapi.testclient import TestClient

from app.core.context import UserContext, UserRole
from app.core.security import get_current_user
from app.db.copilot import get_copilot_session
from app.main import create_app
from config.settings import Settings, get_settings


@pytest.fixture
def client():
    app = create_app()
    admin_ctx = UserContext(
        trace_id="t-admin",
        user_id=1,
        username="admin",
        role=UserRole.ADMIN,
    )

    async def _user():
        return admin_ctx

    async def _session():
        yield AsyncMockSession()

    class AsyncMockSession:
        async def commit(self):
            pass

        async def execute(self, *args, **kwargs):
            return None

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_copilot_session] = _session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_research_disabled_returns_503():
    app = create_app()
    admin_ctx = UserContext(
        trace_id="t-admin",
        user_id=1,
        username="admin",
        role=UserRole.ADMIN,
    )

    async def _user():
        return admin_ctx

    async def _session():
        class S:
            async def commit(self):
                pass

        yield S()

    def _settings_disabled():
        s = Settings()
        s.research_enabled = False
        return s

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_copilot_session] = _session
    app.dependency_overrides[get_settings] = _settings_disabled
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/research/report",
            json={"requestText": "测试"},
            headers={"Authorization": "Bearer fake"},
        )
        assert resp.status_code == 503
        body = resp.json()
        err = body.get("error") or body.get("detail", {}).get("error")
        assert err["code"] == "RESEARCH_DISABLED"
    app.dependency_overrides.clear()


def test_list_reports_empty(client, monkeypatch):
    async def _empty(*args, **kwargs):
        return []

    monkeypatch.setattr("app.api.research.repo.list_reports", _empty)
    resp = client.get("/api/v1/research/report", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert resp.json() == []
