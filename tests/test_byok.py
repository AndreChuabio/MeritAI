"""A user-supplied gateway key is used for the request and never persisted."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.byok import RequireLLMKey
from paperpilot import gateway


@pytest.fixture(autouse=True)
def _clear_request_key():
    yield
    gateway.set_request_key(None)


def test_request_key_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "server-key")
    gateway.set_request_key("user-key")
    client = gateway.get_client()
    assert client.api_key == "user-key"


def test_falls_back_to_env_when_no_request_key(monkeypatch):
    """Track runs on Merit's key: no request key means use the server's."""
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "server-key")
    gateway.set_request_key(None)
    client = gateway.get_client()
    assert client.api_key == "server-key"


def test_raises_when_neither_key_present(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    gateway.set_request_key(None)
    with pytest.raises(RuntimeError, match="No LLM API key"):
        gateway.get_client()


def test_dependency_binds_header_key():
    app = FastAPI()

    @app.get("/probe")
    def probe(_: None = RequireLLMKey) -> dict:
        return {"key": gateway.get_client().api_key}

    with TestClient(app) as client:
        resp = client.get("/probe", headers={"X-LLM-Key": "byok-abc"})
    assert resp.status_code == 200
    assert resp.json() == {"key": "byok-abc"}


def test_dependency_rejects_missing_header():
    app = FastAPI()

    @app.get("/probe")
    def probe(_: None = RequireLLMKey) -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        resp = client.get("/probe")
    assert resp.status_code == 400
    assert "X-LLM-Key" in resp.json()["detail"]
