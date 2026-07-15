"""Cost and quota queries read the trace ledger."""

import fnmatch
import inspect
from datetime import datetime

from paperpilot import supabase_client


def test_user_cost_usd_exists_with_expected_signature():
    sig = inspect.signature(supabase_client.user_cost_usd)
    assert list(sig.parameters) == ["user_id", "since", "conn"]


def test_user_event_count_exists_with_expected_signature():
    sig = inspect.signature(supabase_client.user_event_count)
    assert list(sig.parameters) == ["user_id", "kind_prefix", "since", "conn"]


def test_user_cost_usd_sums_payload_cost(monkeypatch):
    """The query sums payload->>'cost_usd' for one user."""
    captured = {}

    class FakeCursor:
        def fetchone(self):
            return (0.42,)

    class FakeConn:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())
    total = supabase_client.user_cost_usd("user-1")
    assert total == 0.42
    assert "cost_usd" in captured["sql"]
    assert captured["params"][0] == "user-1"


def test_user_cost_usd_with_since_includes_it_in_params(monkeypatch):
    """Exercises the since-is-not-None branch.

    The SQL is "(%s IS NULL OR ts >= %s)" -- since must be threaded through
    to both placeholders, not just checked for None in Python.
    """
    captured = {}

    class FakeCursor:
        def fetchone(self):
            return (1.5,)

    class FakeConn:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())
    since = datetime(2026, 6, 1)
    total = supabase_client.user_cost_usd("user-1", since)

    assert total == 1.5
    assert captured["params"] == ("user-1", since, since)


def test_user_cost_usd_closes_the_connection_it_owns(monkeypatch):
    """When no conn is passed in, user_cost_usd() must check one out via
    get_conn() and close it itself. Callers that pass conn= explicitly
    (e.g. inside a larger transaction) own the close instead -- this test
    only covers the owns=True path.
    """
    closed = {"called": False}

    class FakeCursor:
        def fetchone(self):
            return (0.0,)

    class FakeConn:
        def execute(self, sql, params):
            return FakeCursor()

        def close(self):
            closed["called"] = True

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())
    supabase_client.user_cost_usd("user-1")

    assert closed["called"] is True


def test_user_event_count_is_parameterized_and_returns_count(monkeypatch):
    """user_event_count must bind kind_prefix as a query parameter, never
    format it into the SQL text -- this is the exact mechanism a later
    quota-enforcement task depends on, so an injection-shaped bug here would
    silently miscount every user's quota usage.
    """
    captured = {}

    class FakeCursor:
        def fetchone(self):
            return (7,)

    class FakeConn:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())
    since = datetime(2026, 1, 1)
    count = supabase_client.user_event_count("user-1", "evidence_draft", since)

    assert count == 7
    assert "%s" in captured["sql"]
    assert "evidence_draft" not in captured["sql"]
    assert captured["params"] == ("user-1", "evidence_draft%.end", since)


def test_user_event_count_like_pattern_matches_real_emitted_kind(monkeypatch):
    """Proves the '%.end' suffix actually matches real trace kinds.

    trace.step() (paperpilot/trace.py) logs an end event as f"{kind}.end",
    and evidence_draft narratives call trace.step(sid, f"evidence_draft.
    {criterion}", ...) (paperpilot/outreach/evidence_draft.py), so a
    completed 'awards' draft is logged with kind
    "evidence_draft.awards.end". This locks in WHY user_event_count builds
    the pattern as "<kind_prefix>%.end" rather than "<kind_prefix>.end" or
    "<kind_prefix>%" -- the criterion sits between the prefix and the
    suffix.
    """
    captured = {}

    class FakeCursor:
        def fetchone(self):
            return (0,)

    class FakeConn:
        def execute(self, sql, params):
            captured["params"] = params
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())
    supabase_client.user_event_count("user-1", "evidence_draft", datetime.now())

    like_pattern = captured["params"][1]
    fnmatch_pattern = like_pattern.replace("%", "*")

    real_emitted_kind = "evidence_draft.awards.end"
    assert fnmatch.fnmatch(real_emitted_kind, fnmatch_pattern)
