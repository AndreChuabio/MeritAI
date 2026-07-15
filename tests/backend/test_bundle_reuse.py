"""Plugin extraction reuses the bundle ingest already paid to fetch.

/ingest fetches and renders the repo bundle (up to 600K tokens) and sends it
to Gemini once. /extract-plugin used to re-fetch and re-send the same bundle,
doubling the GitHub fetch and the bundle-assembly cost of a Productize run on
the user's own key. It now reads the bundle ingest already stored instead of
re-fetching, and only falls back to a fresh fetch for a plugin-only run that
never called /ingest.

A large bundle still costs real money even when it is only sent once, so
ingest also refuses to proceed past a token threshold until the caller
explicitly confirms.
"""

import pytest
from fastapi import HTTPException

from backend.services import ingest_service, plugin_service


def test_plugin_reuses_stored_bundle(monkeypatch):
    """When a repo_bundle artifact exists for the session, GitHub is not re-hit."""
    monkeypatch.setattr(
        plugin_service.supabase_client,
        "fetch_artifact_content",
        lambda session_id, kind, user_id=None: "cached bundle text",
    )

    def explode(*args, **kwargs):
        raise AssertionError("must not re-fetch the repo when a bundle is cached")

    monkeypatch.setattr(plugin_service, "fetch_repo_bundle", explode)

    bundle = plugin_service._load_bundle(
        session_id="sess_1",
        user_id="11111111-1111-1111-1111-111111111111",
        repo_url="https://github.com/octocat/hello",
    )
    assert bundle == "cached bundle text"


def test_plugin_refetches_when_no_bundle_cached(monkeypatch):
    """With no cached bundle, fall back to fetching (a plugin-only run)."""
    monkeypatch.setattr(
        plugin_service.supabase_client,
        "fetch_artifact_content",
        lambda session_id, kind, user_id=None: None,
    )
    monkeypatch.setattr(
        plugin_service, "fetch_repo_bundle", lambda repo_url: "freshly fetched"
    )
    bundle = plugin_service._load_bundle(
        session_id="sess_2",
        user_id="11111111-1111-1111-1111-111111111111",
        repo_url="https://github.com/octocat/hello",
    )
    assert bundle == "freshly fetched"


def test_large_bundle_requires_confirmation(monkeypatch):
    """A bundle over the threshold is refused until the caller confirms."""
    monkeypatch.setattr(ingest_service, "MAX_UNCONFIRMED_TOKENS", 100)
    with pytest.raises(HTTPException) as exc:
        ingest_service.check_bundle_size(estimated_tokens=5_000, confirm_large=False)
    assert exc.value.status_code == 413
    assert "5,000" in exc.value.detail
    assert "confirm" in exc.value.detail.lower()


def test_large_bundle_proceeds_when_confirmed(monkeypatch):
    monkeypatch.setattr(ingest_service, "MAX_UNCONFIRMED_TOKENS", 100)
    ingest_service.check_bundle_size(estimated_tokens=5_000, confirm_large=True)


def test_small_bundle_needs_no_confirmation(monkeypatch):
    monkeypatch.setattr(ingest_service, "MAX_UNCONFIRMED_TOKENS", 100_000)
    ingest_service.check_bundle_size(estimated_tokens=5_000, confirm_large=False)
