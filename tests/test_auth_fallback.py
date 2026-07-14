"""The dev-auth fallback must fail closed once the repo is public."""

import pytest

from paperpilot import auth


def test_no_users_configured_yields_no_users(monkeypatch):
    """Unset PAPERPILOT_USERS_JSON grants no access, not a dev account."""
    monkeypatch.delenv("PAPERPILOT_USERS_JSON", raising=False)
    monkeypatch.delenv("ALLOW_DEV_AUTH", raising=False)
    users, is_fallback = auth._load_users()
    assert users == []
    assert is_fallback is True


def test_malformed_json_yields_no_users(monkeypatch):
    """Malformed config must not silently downgrade to the dev account."""
    monkeypatch.setenv("PAPERPILOT_USERS_JSON", "{not json")
    monkeypatch.delenv("ALLOW_DEV_AUTH", raising=False)
    users, is_fallback = auth._load_users()
    assert users == []
    assert is_fallback is True


def test_dev_user_requires_explicit_opt_in(monkeypatch):
    """The dev account is available only with ALLOW_DEV_AUTH=1."""
    monkeypatch.delenv("PAPERPILOT_USERS_JSON", raising=False)
    monkeypatch.setenv("ALLOW_DEV_AUTH", "1")
    users, is_fallback = auth._load_users()
    assert len(users) == 1
    assert users[0]["user_id"] == "dev"
    assert is_fallback is True
