"""A user can get their data out and can delete it."""

from fastapi.testclient import TestClient

from backend.auth import AuthUser, get_current_user
from backend.main import app

USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email="ada@example.com")


def _as_user():
    app.dependency_overrides[get_current_user] = lambda: USER


def test_export_requires_auth():
    with TestClient(app) as client:
        resp = client.get("/account/export")
    assert resp.status_code == 401


def test_delete_requires_auth():
    with TestClient(app) as client:
        resp = client.delete("/account")
    assert resp.status_code == 401


def test_export_returns_every_table_keyed_to_the_user(monkeypatch):
    from backend.routers import account

    monkeypatch.setattr(
        account,
        "_collect_user_data",
        lambda user_id: {
            "profile": {"name": "Ada"},
            "evidence": [{"criterion": "awards"}],
            "outreach_log": [],
            "artifacts": [],
        },
    )
    _as_user()
    try:
        with TestClient(app) as client:
            resp = client.get("/account/export")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"profile", "evidence", "outreach_log", "artifacts"}
    assert body["evidence"][0]["criterion"] == "awards"


def test_delete_removes_the_auth_user(monkeypatch):
    from backend.routers import account

    deleted = []
    monkeypatch.setattr(account, "_delete_user", lambda user_id: deleted.append(user_id))
    _as_user()
    try:
        with TestClient(app) as client:
            resp = client.delete("/account")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204
    assert deleted == [USER.id]
