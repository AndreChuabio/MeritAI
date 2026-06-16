"""Smoke tests for the FastAPI backend that need no live Supabase.

The auth dependency is overridden so route wiring and response shapes can be
asserted without a real token. Endpoints that hit Supabase (match) are covered
by the live verification path, not here.
"""

from fastapi.testclient import TestClient

from backend.auth import AuthUser, get_current_user
from backend.main import app


def test_me_requires_token():
    """Without a bearer token, /me is unauthorized."""
    with TestClient(app) as client:
        resp = client.get("/me")
    assert resp.status_code == 401


def test_me_returns_user_when_authenticated():
    """With the auth dependency satisfied, /me echoes the caller."""
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="00000000-0000-0000-0000-000000000001", email="clown@example.com"
    )
    try:
        with TestClient(app) as client:
            resp = client.get("/me")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "clown@example.com",
    }


def test_health_shape():
    """/health always returns the expected shape and never raises."""
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["database"], bool)
