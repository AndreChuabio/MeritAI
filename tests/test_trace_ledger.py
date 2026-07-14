"""trace.log_event must write to Supabase, not a dead ClickHouse import."""

from paperpilot import trace


def test_log_event_writes_to_supabase(monkeypatch):
    """With SUPABASE_DB_URL set, events reach supabase_client.insert_trace."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    calls = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: calls.append(
            (session_id, user_id, kind, payload)
        ),
    )
    sid = trace.new_session("11111111-1111-1111-1111-111111111111")
    trace.log_event(sid, "test.kind", {"cost_usd": 0.01})

    assert len(calls) == 1
    assert calls[0][0] == sid
    assert calls[0][1] == "11111111-1111-1111-1111-111111111111"
    assert calls[0][2] == "test.kind"
    assert calls[0][3]["cost_usd"] == 0.01


def test_empty_user_id_becomes_null(monkeypatch):
    """A session with no bound user writes NULL, not '', into a uuid column."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    calls = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: calls.append(user_id),
    )
    trace.log_event("sess_orphan", "test.kind", {})
    assert calls == [None]


def test_no_supabase_configured_is_a_noop(monkeypatch):
    """Unconfigured instances buffer in memory and never raise."""
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)

    def explode(*args, **kwargs):
        raise AssertionError("must not write when unconfigured")

    monkeypatch.setattr(trace, "insert_trace", explode)
    trace.log_event("sess_x", "test.kind", {})
    assert trace.buffered_events("sess_x")[-1].kind == "test.kind"


def test_insert_failure_never_raises(monkeypatch):
    """A ledger write failure must not fail the user's run."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(trace, "insert_trace", boom)
    trace.log_event("sess_y", "test.kind", {})
    evt = trace.buffered_events("sess_y")[-1]
    assert any("trace_insert_failed" in w for w in evt.payload["_warn"])
