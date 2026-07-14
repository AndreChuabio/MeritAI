"""Tenancy scoping tests for paperpilot.supabase_client.

The backend connects to Postgres as the service role, which bypasses RLS.
That means the user_id filter applied in application code is the ONLY guard
against one tenant reading another tenant's session_artifacts row. Before
this test existed, fetch_artifact_content's user_id parameter was optional
and defaulted to None, and when None the WHERE clause silently omitted the
user filter entirely -- a caller who forgot to pass user_id read ANY user's
artifacts. tests/backend/test_bundle_reuse.py monkeypatches
fetch_artifact_content with a lambda that ignores user_id, so it could not
have caught this: the SQL/params were never inspected.

These tests capture the actual SQL text and bound params sent to the
connection (FakeConn/FakeCursor pattern, matching tests/test_cost_query.py)
so a regression that drops the user_id clause fails here even if every
other test still passes.
"""

from __future__ import annotations

import inspect

import pytest

from paperpilot import supabase_client


def test_fetch_artifact_content_user_id_has_no_default():
    """user_id must be required -- omitting it should be a TypeError, not a
    silent cross-tenant read at runtime."""
    sig = inspect.signature(supabase_client.fetch_artifact_content)
    assert "user_id" in sig.parameters
    assert sig.parameters["user_id"].default is inspect.Parameter.empty


def test_fetch_artifact_content_omitting_user_id_raises_typeerror():
    with pytest.raises(TypeError):
        supabase_client.fetch_artifact_content("sess_1", "repo_bundle")  # type: ignore[call-arg]


def test_fetch_artifact_content_scopes_sql_and_params_by_user_id(monkeypatch):
    """The generated WHERE clause and the bound params must both carry
    user_id -- proves the tenancy filter can't be silently dropped while
    this test still passes."""
    captured = {}

    class FakeCursor:
        def fetchone(self):
            return ("cached bundle text",)

    class FakeConn:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())

    result = supabase_client.fetch_artifact_content(
        "sess_1", "repo_bundle", "11111111-1111-1111-1111-111111111111"
    )

    assert result == "cached bundle text"
    assert "user_id" in captured["sql"]
    assert "11111111-1111-1111-1111-111111111111" in captured["params"]
    # session_id and artifact_name must still be present -- the fix must add
    # the user_id filter, not replace the existing scoping.
    assert "sess_1" in captured["params"]
    assert "repo_bundle" in captured["params"]


def test_fetch_artifact_content_two_users_same_session_get_different_sql_scope(
    monkeypatch,
):
    """Regression guard for the exact bug described in the review: calling
    with a different user_id must change the bound params, not just be
    accepted and ignored."""
    seen_params = []

    class FakeCursor:
        def fetchone(self):
            return None

    class FakeConn:
        def execute(self, sql, params):
            seen_params.append(tuple(params))
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())

    supabase_client.fetch_artifact_content("sess_shared", "repo_bundle", "user-a")
    supabase_client.fetch_artifact_content("sess_shared", "repo_bundle", "user-b")

    assert seen_params[0] != seen_params[1]
    assert "user-a" in seen_params[0]
    assert "user-b" in seen_params[1]


# ---------------------------------------------------------------------------
# session_owner: backs the session_id ownership check for POST /extract-plugin.
# ---------------------------------------------------------------------------


def test_session_owner_returns_none_for_unknown_session(monkeypatch):
    class FakeCursor:
        def fetchone(self):
            return None

    class FakeConn:
        def execute(self, sql, params):
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())

    assert supabase_client.session_owner("sess_fresh") is None


def test_session_owner_returns_existing_owner_from_session_artifacts(monkeypatch):
    captured_sql = []

    class FakeCursor:
        def fetchone(self):
            return ("owner-user-id",)

    class FakeConn:
        def execute(self, sql, params):
            captured_sql.append(sql)
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())

    owner = supabase_client.session_owner("sess_owned")

    assert owner == "owner-user-id"
    assert any("session_artifacts" in sql for sql in captured_sql)


def test_session_owner_falls_back_to_trace_log(monkeypatch):
    """If session_artifacts has no row yet (e.g. only a trace was written so
    far), trace_log must still be checked before declaring the session
    unowned."""
    calls = []

    class FakeCursor:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class FakeConn:
        def execute(self, sql, params):
            calls.append(sql)
            if "session_artifacts" in sql:
                return FakeCursor(None)
            return FakeCursor(("trace-owner-id",))

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())

    owner = supabase_client.session_owner("sess_trace_only")

    assert owner == "trace-owner-id"
    assert len(calls) == 2
