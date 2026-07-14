"""Trace event helper.

This is our redundancy against Lapdog. Every meaningful agent step calls
log_event(); rows land in Supabase trace_log AND we keep them in process
memory so the Streamlit UI can render them live without round-tripping to
the database.

Multi-tenancy: every session is bound to a user_id at creation time.
Subsequent log_event / step calls automatically attach that user_id to
trace_log inserts so reads can be filtered per user.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from time import time
from typing import Any, Iterator

from paperpilot.supabase_client import insert_trace


def _ledger_configured() -> bool:
    """True when a Supabase connection string is available to write traces to."""
    return bool(os.environ.get("SUPABASE_DB_URL"))


@dataclass
class TraceEvent:
    session_id: str
    ts: float
    kind: str
    payload: dict[str, Any]


# In-process buffer keyed by session_id so the UI can render without a
# round-trip to the database.
_BUFFER: dict[str, list[TraceEvent]] = {}

# Session-id -> user_id binding established at new_session() time. log_event
# and step() auto-pull user_id from here so every trace_log row carries the
# right tenant.
_SESSION_USER: dict[str, str] = {}


def new_session(user_id: str) -> str:
    """Generate a session id used to group an end-to-end Merit run.

    The user_id is bound to this session id and used for all subsequent
    log_event / step calls referencing it.
    """
    if not user_id:
        raise ValueError("user_id is required to start a session")
    sid = f"sess_{uuid.uuid4().hex[:12]}"
    _SESSION_USER[sid] = user_id
    return sid


def session_user(session_id: str) -> str:
    """Return the user_id bound to a session, or empty string if unknown."""
    return _SESSION_USER.get(session_id, "")


def log_event(session_id: str, kind: str, payload: dict[str, Any]) -> None:
    """Record one agent step. Best-effort writes to Supabase; never raises.

    user_id for the trace_log row is resolved from the session binding set
    by new_session(). Sessions created outside that helper produce rows
    with a NULL user_id (legacy/system path) -- trace_log.user_id is a uuid
    column, so an unbound session must write NULL, not the empty string.
    """
    evt = TraceEvent(session_id=session_id, ts=time(), kind=kind, payload=payload)
    _BUFFER.setdefault(session_id, []).append(evt)
    if not _ledger_configured():
        return
    # trace_log.user_id is a uuid column: an unbound session must write NULL,
    # not the empty string, or the insert fails on the cast.
    user_id = _SESSION_USER.get(session_id) or None
    try:
        insert_trace(session_id, user_id, kind, payload)
    except Exception as exc:  # noqa: BLE001 -- best-effort; never fail the run
        # Surface but don't crash. The buffer still has the event.
        evt.payload.setdefault("_warn", []).append(f"trace_insert_failed: {exc!s}")


def buffered_events(session_id: str) -> list[TraceEvent]:
    """Return the in-process trace buffer for live UI rendering."""
    return list(_BUFFER.get(session_id, []))


@contextmanager
def step(session_id: str, kind: str, **payload: Any) -> Iterator[dict[str, Any]]:
    """Context manager that times a step and records start/end events.

    Usage:
        with step(sid, "ingest.gemini", repo=url) as ctx:
            ctx["tokens_in"] = ...
    """
    start = time()
    log_event(session_id, f"{kind}.start", {**payload})
    ctx: dict[str, Any] = {}
    try:
        yield ctx
    except Exception as exc:  # noqa: BLE001
        log_event(
            session_id,
            f"{kind}.error",
            {**payload, **ctx, "error": str(exc), "dur_ms": int((time() - start) * 1000)},
        )
        raise
    else:
        log_event(
            session_id,
            f"{kind}.end",
            {**payload, **ctx, "dur_ms": int((time() - start) * 1000)},
        )
