"""The user's API key must not reach any log, trace, or database row."""

import logging

from paperpilot import trace
from paperpilot.redaction import RedactKeyFilter, SENSITIVE_KEYS

SECRET = "vck_super_secret_user_key"


def test_trace_payload_scrubs_sensitive_keys(monkeypatch):
    """A key accidentally passed into a trace payload is redacted before insert."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    written = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: written.append(payload),
    )
    sid = trace.new_session("11111111-1111-1111-1111-111111111111")
    trace.log_event(sid, "ingest.start", {"api_key": SECRET, "repo": "octocat/hello"})

    assert written[0]["api_key"] == "[REDACTED]"
    assert written[0]["repo"] == "octocat/hello"


def test_trace_payload_scrubs_nested(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    written = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: written.append(payload),
    )
    trace.log_event("s1", "k", {"headers": {"x-llm-key": SECRET}})
    assert written[0]["headers"]["x-llm-key"] == "[REDACTED]"


def test_log_filter_redacts_key_in_message():
    """A key that lands in a log message is redacted before it is emitted."""
    filt = RedactKeyFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="calling gateway with X-LLM-Key: %s",
        args=(SECRET,),
        exc_info=None,
    )
    filt.filter(record)
    assert SECRET not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_sensitive_key_names_cover_the_header():
    assert "x-llm-key" in SENSITIVE_KEYS
    assert "api_key" in SENSITIVE_KEYS
