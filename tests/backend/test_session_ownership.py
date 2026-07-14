"""POST /extract-plugin must not let a caller write into another user's
session namespace via a guessed or reused session_id.

Reads are already safe: fetch_artifact_content filters by user_id, so a
caller passing another user's session_id just gets no cached bundle and
falls back to a fresh fetch (see test_bundle_reuse.py /
test_supabase_client_tenancy.py). Writes are not -- trace.step (via
extract_plugin) and insert_artifact would happily write rows keyed to that
other user's session_id. extract_plugin_from_repo must reject a
caller-supplied session_id that is already owned by a different user_id,
and must allow a session_id with no known owner (a fresh session).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.services import plugin_service


OTHER_USER = "22222222-2222-2222-2222-222222222222"
CALLING_USER = "11111111-1111-1111-1111-111111111111"


def test_check_session_ownership_allows_unknown_session(monkeypatch):
    """A session_id with no recorded owner is a fresh session -- allowed."""
    monkeypatch.setattr(
        plugin_service.supabase_client, "session_owner", lambda session_id: None
    )
    plugin_service._check_session_ownership("sess_fresh", CALLING_USER)  # no raise


def test_check_session_ownership_allows_own_session(monkeypatch):
    monkeypatch.setattr(
        plugin_service.supabase_client,
        "session_owner",
        lambda session_id: CALLING_USER,
    )
    plugin_service._check_session_ownership("sess_mine", CALLING_USER)  # no raise


def test_check_session_ownership_rejects_other_users_session(monkeypatch):
    monkeypatch.setattr(
        plugin_service.supabase_client, "session_owner", lambda session_id: OTHER_USER
    )
    with pytest.raises(HTTPException) as exc:
        plugin_service._check_session_ownership("sess_not_mine", CALLING_USER)
    assert exc.value.status_code == 403


def test_extract_plugin_from_repo_rejects_other_users_session_id(monkeypatch):
    """End-to-end: extract_plugin_from_repo must reject before touching the
    bundle, the LLM, or persistence when session_id belongs to someone else."""
    monkeypatch.setattr(
        plugin_service.supabase_client, "session_owner", lambda session_id: OTHER_USER
    )

    def explode(*args, **kwargs):
        raise AssertionError("must not proceed past the ownership check")

    monkeypatch.setattr(plugin_service, "_load_bundle", explode)
    monkeypatch.setattr(plugin_service, "extract_plugin", explode)

    with pytest.raises(HTTPException) as exc:
        plugin_service.extract_plugin_from_repo(
            "https://github.com/octocat/hello",
            CALLING_USER,
            session_id="sess_not_mine",
        )
    assert exc.value.status_code == 403


def test_extract_plugin_from_repo_allows_unknown_session_id(monkeypatch):
    """A session_id with no recorded owner (fresh session, or a plugin-only
    run reusing a client-generated id) must proceed normally."""
    monkeypatch.setattr(
        plugin_service.supabase_client, "session_owner", lambda session_id: None
    )
    monkeypatch.setattr(
        plugin_service, "_load_bundle", lambda **kwargs: "rendered bundle text"
    )

    class FakePack:
        total_artifacts = 1
        skills = commands = agents = hooks = mcps = []
        plugin_name = "demo-plugin"

    monkeypatch.setattr(
        plugin_service, "extract_plugin", lambda rendered, sid, repo_label="": FakePack()
    )
    monkeypatch.setattr(
        plugin_service, "build_plugin_zip", lambda pack, label: b"zip-bytes"
    )
    monkeypatch.setattr(
        plugin_service,
        "render_plugin_manifest",
        lambda pack, label: '{"name": "demo-plugin"}',
    )
    monkeypatch.setattr(
        plugin_service.supabase_client, "insert_artifact", lambda *a, **kw: None
    )

    result = plugin_service.extract_plugin_from_repo(
        "https://github.com/octocat/hello",
        CALLING_USER,
        session_id="sess_fresh",
    )
    assert result.plugin_name == "demo-plugin"
