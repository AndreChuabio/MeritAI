"""Assist router: stream an O-1A coaching answer as SSE.

POST /assist accepts a plain-English question, the surface the user is on
(track / productize / market), and an optional page-context dict. It streams a
coaching answer token by token through the AI Gateway so the "Help me"
assistant can render the reply live.

Event types emitted (the SSE `event:` field):
  - "delta": a streamed text chunk. data = {"text"}.
  - "done": the answer finished. data = {"session_id"}.
  - "error": generation failed. data = {"message"}.

Modeled on backend.routers.draft: a synchronous Gateway-backed generator is
driven off the event loop with starlette iterate_in_threadpool, and each step
is wrapped as a Server-Sent Event.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from backend.auth import AuthUser, CurrentUser
from backend.services.assist_service import assist_answer
from paperpilot import trace

router = APIRouter(tags=["assist"])


class AssistRequest(BaseModel):
    """Request body for POST /assist."""

    question: str
    surface: str = "track"
    context: dict[str, Any] | None = None


def _sse(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Format an SSE message for EventSourceResponse."""
    return {"event": event, "data": json.dumps(data, default=str)}


@router.post("/assist", response_model=None)
async def assist(
    req: AssistRequest, user: AuthUser = CurrentUser
) -> EventSourceResponse:
    """Stream a coaching answer to the user's question as Server-Sent Events.

    A new trace session is started for the run, bound to the authenticated
    user so trace rows are tenant-scoped.
    """
    session_id = trace.new_session(user.id)

    async def event_stream() -> AsyncIterator[dict[str, Any]]:
        """Drive the blocking Gateway generator off the loop and emit SSE."""
        gen = assist_answer(
            req.question, req.surface, req.context, session_id
        )
        try:
            async for delta in iterate_in_threadpool(gen):
                yield _sse("delta", {"text": delta})
            yield _sse("done", {"session_id": session_id})
        except Exception as exc:  # noqa: BLE001 -- surface to client, end stream
            yield _sse("error", {"message": str(exc)})

    return EventSourceResponse(event_stream())
