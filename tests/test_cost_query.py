"""Cost and quota queries read the trace ledger."""

import inspect

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
