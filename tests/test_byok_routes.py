"""Pins RequireLLMKey to the production BYOK routes.

If `_: None = RequireLLMKey` is ever removed from one of these route
signatures, this test catches it: the request would stop being rejected for
a missing X-LLM-Key header. Auth is overridden so the assertion is purely
about the key requirement, not the caller's identity.
"""

from fastapi.testclient import TestClient

from backend.auth import AuthUser, get_current_user
from backend.main import app

_USER = AuthUser(id="00000000-0000-0000-0000-000000000001", email="clown@example.com")

_RESEARCH_SUMMARY = {
    "problem": "p",
    "contribution": "c",
    "method": "m",
    "results": "r",
    "limitations": "l",
}

_BYOK_ROUTES = [
    ("POST", "/ingest", {"repo_url": "https://github.com/octocat/hello"}),
    (
        "POST",
        "/draft",
        {
            "summary": _RESEARCH_SUMMARY,
            "venue": {"name": "ICML"},
        },
    ),
    ("POST", "/extract-plugin", {"repo_url": "https://github.com/octocat/hello"}),
    ("POST", "/match", {"summary": _RESEARCH_SUMMARY}),
    (
        "POST",
        "/market/outreach/generate",
        {"purpose": "CAREER", "context": "ctx"},
    ),
]


def test_byok_routes_reject_missing_key():
    """Each production BYOK route 400s without an X-LLM-Key header."""
    app.dependency_overrides[get_current_user] = lambda: _USER
    try:
        with TestClient(app) as client:
            for method, path, body in _BYOK_ROUTES:
                resp = client.request(method, path, json=body)
                assert resp.status_code == 400, (
                    f"{method} {path} returned {resp.status_code}, expected 400 "
                    "without X-LLM-Key"
                )
                assert "X-LLM-Key" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_track_route_does_not_require_llm_key():
    """A Track route (evidence ledger) must not 400 for a missing X-LLM-Key."""
    app.dependency_overrides[get_current_user] = lambda: _USER
    try:
        with TestClient(app) as client:
            resp = client.get("/evidence")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code != 400
