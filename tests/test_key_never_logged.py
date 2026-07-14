"""The user's API key must not reach any log, trace, or database row."""

import io
import logging

from paperpilot import gateway, redaction, trace
from paperpilot.redaction import RedactKeyFilter, SENSITIVE_KEYS

SECRET = "vck_super_secret_user_key"

# byok.require_llm_key accepts any non-empty string as a gateway key -- it is
# not required to match one of the shape patterns below. This key matches
# none of them, so only literal substitution of the bound request key (not
# _SECRET_PATTERNS) can catch it.
NON_SHAPED_SECRET = "gw-live-1234567890abcdef"


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


def _capture_via_real_handler() -> tuple[io.StringIO, logging.StreamHandler, logging.Logger]:
    """Attach a real StreamHandler+Formatter to root, like production wiring.

    caplog can bypass normal handler formatting, so the tests below drive a
    genuine StreamHandler over a StringIO with a real Formatter -- the same
    path a shape-only redactor was previously proven to leak through.
    """
    redaction.install()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return stream, handler, root


def test_literal_bound_key_redacted_when_shape_matches_nothing():
    """byok.require_llm_key accepts ANY non-empty string as the gateway key,
    not just vck_/sk-ant-/sk-/AIza shapes. A key outside those shapes must
    still be redacted once it is bound as the current request's key, or the
    no-custody promise silently fails for every non-Vercel-shaped key."""
    stream, handler, root = _capture_via_real_handler()
    gateway.set_request_key(NON_SHAPED_SECRET)
    try:
        logging.getLogger("paperpilot.pipeline").warning(
            "calling gateway with key %s", NON_SHAPED_SECRET
        )
    finally:
        gateway.set_request_key(None)
        root.removeHandler(handler)

    output = stream.getvalue()
    assert NON_SHAPED_SECRET not in output
    assert "[REDACTED]" in output


def test_literal_bound_key_redacted_in_traceback():
    """The same non-shaped key, echoed back inside an exception traceback
    (e.g. an upstream SDK's AuthenticationError message), must also be
    redacted -- not just the log message template."""
    stream, handler, root = _capture_via_real_handler()
    gateway.set_request_key(NON_SHAPED_SECRET)
    try:
        try:
            raise RuntimeError(f"Incorrect API key provided: {NON_SHAPED_SECRET}")
        except RuntimeError:
            logging.getLogger("paperpilot.pipeline").exception("draft failed")
    finally:
        gateway.set_request_key(None)
        root.removeHandler(handler)

    output = stream.getvalue()
    assert NON_SHAPED_SECRET not in output
    assert "[REDACTED]" in output


def test_short_bound_key_does_not_corrupt_unrelated_log_text():
    """A degenerate bound key (empty, or too short to be a real credential)
    must not turn substring matches in unrelated log text into [REDACTED].
    Substituting a 3-character key would corrupt any log line that happens
    to contain that substring."""
    stream, handler, root = _capture_via_real_handler()
    gateway.set_request_key("abc")
    try:
        logging.getLogger("paperpilot.pipeline").warning(
            "fetched abcdef123 from cache, abcxyz unaffected"
        )
    finally:
        gateway.set_request_key(None)
        root.removeHandler(handler)

    output = stream.getvalue()
    assert "abcdef123" in output
    assert "abcxyz" in output
    assert "[REDACTED]" not in output


def test_shape_pattern_still_redacts_with_no_key_bound():
    """With nothing bound to the request context (env-var key, other
    providers, or a surface that never calls set_request_key), the existing
    shape patterns must keep working exactly as before."""
    stream, handler, root = _capture_via_real_handler()
    gateway.set_request_key(None)
    try:
        logging.getLogger("paperpilot.pipeline").warning("key %s", SECRET)
    finally:
        root.removeHandler(handler)

    output = stream.getvalue()
    assert SECRET not in output
    assert "[REDACTED]" in output
