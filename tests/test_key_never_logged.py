"""The user's API key must not reach any log, trace, or database row."""

import io
import logging

from paperpilot import redaction, trace
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


def test_module_logger_is_redacted_end_to_end(caplog):
    """Every module logger (logging.getLogger(__name__)) must be redacted,
    not just root/uvicorn. install() previously only attached a filter to
    named loggers, and Logger.callHandlers() never consults an ancestor's
    filters -- only its handlers -- so module-logger records sailed through
    unredacted."""
    redaction.install()
    logging.getLogger("paperpilot.pipeline").warning("key %s", SECRET)
    assert SECRET not in caplog.text


def test_traceback_is_redacted(caplog):
    """logging.Formatter.format() appends formatException(record.exc_info)
    independently of record.msg. A filter that only rewrites msg leaves the
    traceback -- which can contain the secret verbatim from an upstream
    exception message -- untouched."""
    redaction.install()
    try:
        raise RuntimeError(f"Incorrect API key provided: {SECRET}")
    except RuntimeError:
        logging.getLogger("paperpilot.pipeline").exception("draft failed")
    assert SECRET not in caplog.text


def test_module_logger_redacted_in_real_handler_output():
    """caplog can bypass normal handler formatting, so this test proves the
    real-world path: a module logger propagating to a root StreamHandler
    with a real Formatter must not leak the secret in the formatted text,
    including the formatted traceback."""
    redaction.install()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        logger = logging.getLogger("paperpilot.pipeline")
        logger.warning("key %s", SECRET)
        try:
            raise RuntimeError(f"Incorrect API key provided: {SECRET}")
        except RuntimeError:
            logger.exception("draft failed")
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)

    output = stream.getvalue()
    assert SECRET not in output
    assert "[REDACTED]" in output
