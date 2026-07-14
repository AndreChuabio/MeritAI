"""Redaction of user-supplied secrets from anything that gets emitted.

Merit takes no custody of user API keys, which means a key must never survive
into a log line, a Datadog span, or a trace payload. This module is the single
definition of what counts as sensitive, used by both the logging filter and
paperpilot.trace's payload scrubber.

Lives in paperpilot rather than backend because paperpilot.trace needs it and
backend already depends on paperpilot -- the reverse would be circular.
"""

from __future__ import annotations

import logging
import re

REDACTED = "[REDACTED]"

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
    """Replace anything that looks like a credential in free text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class RedactKeyFilter(logging.Filter):
    """Strip credentials from log records before they are emitted anywhere."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 -- never break logging
            return True
        cleaned = redact_text(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def install() -> None:
    """Attach the redaction filter to the root logger and uvicorn's loggers."""
    filt = RedactKeyFilter()
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addFilter(filt)
