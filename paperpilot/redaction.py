"""Redaction of user-supplied secrets from anything that gets emitted.

Merit takes no custody of user API keys, which means a key must never survive
into a log line or a trace payload. This module is the single definition of
what counts as sensitive, used by both the logging filter and
paperpilot.trace's payload scrubber. It covers log records and trace_log
payloads only -- it does not cover APM instrumentation. If ddtrace is enabled
for the API service (e.g. run under ddtrace-run), provider integrations such
as ddtrace's OpenAI integration can tag request metadata (including partial
key material) onto spans independently of this module, and that surface must
be configured or scrubbed separately if and when ddtrace is turned on.

Lives in paperpilot rather than backend because paperpilot.trace needs it and
backend already depends on paperpilot -- the reverse would be circular.

redact_text also imports paperpilot.gateway to reach the literal key bound
to the current request (gateway.current_request_key()). This direction is
safe: gateway.py has no imports from paperpilot, so redaction -> gateway
cannot cycle back. gateway.py must never import this module.
"""

from __future__ import annotations

import logging
import re
import traceback

from paperpilot import gateway

REDACTED = "[REDACTED]"

# byok.require_llm_key accepts any non-empty string as a gateway key, so a
# key that matches none of _SECRET_PATTERNS below is otherwise logged in
# full. Below this length, substituting the bound key risks corrupting
# unrelated log text that happens to contain the same short substring, so a
# degenerate bound key (empty string, or shorter than this) is skipped.
_MIN_BOUND_KEY_LENGTH = 8

# Field names whose values are secrets, lowercased for comparison.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "x-llm-key",
        "x_llm_key",
        "api_key",
        "apikey",
        "authorization",
        "ai_gateway_api_key",
        "senso_api_key",
        "nimble_api_key",
        "github_token",
        "supabase_service_role_key",
    }
)

# Value shapes that are secrets regardless of the field they appear in.
_SECRET_PATTERNS = [
    re.compile(r"vck_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
]


def redact_text(text: str) -> str:
    """Replace anything that looks like a credential in free text.

    Two independent mechanisms, both applied:
    1. Shape patterns (_SECRET_PATTERNS) -- catches keys from env vars,
       other providers, or any surface that never binds a request key.
    2. The literal key bound to the current request via
       gateway.set_request_key(), if any -- catches BYOK keys that do not
       match any known shape, since byok.require_llm_key accepts any
       non-empty string. Skipped if nothing is bound or the bound value is
       too short to be a real credential (see _MIN_BOUND_KEY_LENGTH).
    """
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    bound_key = gateway.current_request_key()
    if bound_key and len(bound_key) >= _MIN_BOUND_KEY_LENGTH:
        text = text.replace(bound_key, REDACTED)
    return text


def _redact_message(record: logging.LogRecord) -> None:
    """Rewrite record.msg/args in place if the rendered message has a secret."""
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001 -- never break logging
        return
    cleaned = redact_text(message)
    if cleaned != message:
        record.msg = cleaned
        record.args = ()


def _redact_traceback(record: logging.LogRecord) -> None:
    """Pre-populate record.exc_text with a redacted, formatted traceback.

    logging.Formatter.format() calls formatException(record.exc_info)
    SEPARATELY from formatting record.msg, and only if record.exc_text is
    not already set (it caches the result on the record). Rewriting msg
    alone therefore never touches the traceback text -- a secret echoed
    back by an upstream exception (e.g. an SDK's AuthenticationError)
    survives straight into the formatted log line. Pre-computing a
    redacted exc_text here is what makes the fix stick regardless of which
    Formatter eventually renders the record.
    """
    if not record.exc_info:
        return
    try:
        formatted = "".join(traceback.format_exception(*record.exc_info))
    except Exception:  # noqa: BLE001 -- never break logging
        return
    if formatted.endswith("\n"):
        formatted = formatted[:-1]
    record.exc_text = redact_text(formatted)


def _redact_stack_info(record: logging.LogRecord) -> None:
    """Redact record.stack_info, which Formatter.format() appends verbatim."""
    stack_info = getattr(record, "stack_info", None)
    if stack_info:
        try:
            record.stack_info = redact_text(stack_info)
        except Exception:  # noqa: BLE001 -- never break logging
            pass


class RedactKeyFilter(logging.Filter):
    """Strip credentials from log records before they are emitted anywhere.

    Kept as defense-in-depth (attached to handlers/loggers by install()),
    but the LogRecordFactory installed below is what actually guarantees
    redaction -- see install()'s docstring.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        _redact_message(record)
        _redact_traceback(record)
        _redact_stack_info(record)
        return True


_installed = False


def install() -> None:
    """Make redaction independent of logger and handler topology.

    Every logging call in this repo uses a module logger
    (logging.getLogger(__name__)) -- 26+ sites. Python's Logger.handle()
    only consults FILTERS on the logger where the record originated;
    Logger.callHandlers() then walks ancestors and invokes their HANDLERS,
    never their filters. So attaching a filter only to the root and
    uvicorn loggers (the previous approach) never redacted any module
    logger's records -- only records logged directly to those exact
    logger names.

    logging.setLogRecordFactory wraps the record constructor itself, which
    every logger (module or otherwise) calls to build its LogRecord before
    any filter or handler is consulted. Wrapping it here means every
    record is redacted -- message, interpolated args, and traceback --
    regardless of which logger emitted it or what handlers exist anywhere
    in the hierarchy.

    Idempotent: calling this more than once (e.g. both backend.main and a
    test) does not double-wrap the factory.
    """
    global _installed
    if _installed:
        return

    base_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = base_factory(*args, **kwargs)
        _redact_message(record)
        _redact_traceback(record)
        _redact_stack_info(record)
        return record

    logging.setLogRecordFactory(factory)

    # Defense-in-depth: also attach the filter to root/uvicorn loggers so
    # anything that bypasses the factory (e.g. a handler-level filter
    # someone adds later, or a record built by hand) still gets a second
    # pass.
    filt = RedactKeyFilter()
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addFilter(filt)

    _installed = True
