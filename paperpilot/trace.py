"""Trace event helper.

This is our redundancy against Lapdog. Every meaningful agent step calls
log_event(); rows land in ClickHouse trace_log AND we keep them in process
memory so the Streamlit UI can render them live without round-tripping to CH.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import time
from typing import Any, Iterator

from paperpilot.clickhouse_client import insert_trace


# clickhouse_connect prints "Unexpected Http Driver Exception" to a logger
# before raising; silence it so half-configured local runs are not noisy.
logging.getLogger("clickhouse_connect.driver.httpclient").setLevel(logging.CRITICAL)
logging.getLogger("clickhouse_connect").setLevel(logging.CRITICAL)


def _clickhouse_configured() -> bool:
    return bool(os.environ.get("CLICKHOUSE_HOST"))


@dataclass
class TraceEvent:
    session_id: str
    ts: float
    kind: str
    payload: dict[str, Any]


# In-process buffer keyed by session_id so the UI can render without CH round-trip.
_BUFFER: dict[str, list[TraceEvent]] = {}


def new_session() -> str:
    """Generate a session id used to group an end-to-end PaperPilot run."""
    return f"sess_{uuid.uuid4().hex[:12]}"


def log_event(session_id: str, kind: str, payload: dict[str, Any]) -> None:
    """Record one agent step. Best-effort writes to ClickHouse; never raises."""
    evt = TraceEvent(session_id=session_id, ts=time(), kind=kind, payload=payload)
    _BUFFER.setdefault(session_id, []).append(evt)
    if not _clickhouse_configured():
        return
    try:
        insert_trace(session_id, kind, payload)
    except Exception as exc:  # noqa: BLE001 -- demo path; we never fail the run
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
