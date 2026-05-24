"""Senso knowledge-base client.

Two operations we use:
  1. `ingest_raw(title, text)` — POST /org/kb/raw with a JSON body containing
     title + text. Seeds the KB with tone-reference content for the drafter.
  2. `search_context(query, max_results)` — POST /org/search/context to
     retrieve relevant chunks from the seeded KB. Used to inject venue/tone
     context into Claude's drafting prompt.

Both calls are wrapped in `trace.step("senso.*")` so they show up on the
agent trace + cost pill + Lapdog/Datadog. Hard timeouts so a slow Senso
cannot break the draft path.

Auth: `X-API-Key: $SENSO_API_KEY`. Base URL configurable via env
`SENSO_BASE_URL` (defaults to the public CLI default).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from paperpilot import trace


SENSO_BASE_URL = os.environ.get("SENSO_BASE_URL", "https://apiv2.senso.ai/api/v1")
SENSO_TIMEOUT_S = 12.0


@dataclass
class ContextChunk:
    text: str
    score: float
    source: str


def is_configured() -> bool:
    return bool(os.environ.get("SENSO_API_KEY"))


def _headers() -> dict[str, str]:
    return {
        "X-API-Key": os.environ["SENSO_API_KEY"],
        "Content-Type": "application/json",
    }


def ingest_raw(
    title: str,
    text: str,
    session_id: str,
    tag_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """Create a raw KB node. Returns the API response or None on failure.

    session_id is required; the caller must have already bound a user_id
    to it via trace.new_session() so the trace.step row is tenant-scoped.
    """
    if not is_configured():
        return None

    body: dict[str, Any] = {"title": title, "text": text}
    if tag_ids:
        body["tag_ids"] = tag_ids

    with trace.step(session_id, "senso.ingest", title=title[:80], chars=len(text)) as ctx:
        try:
            resp = httpx.post(
                f"{SENSO_BASE_URL}/org/kb/raw",
                headers=_headers(),
                json=body,
                timeout=SENSO_TIMEOUT_S,
            )
            ctx["status"] = resp.status_code
            if resp.status_code >= 400:
                ctx["error"] = resp.text[:300]
                return None
            data = resp.json()
            ctx["node_id"] = data.get("id") or data.get("node_id")
            return data
        except (httpx.RequestError, ValueError) as exc:
            ctx["error"] = str(exc)
            return None


def search_context(
    query: str,
    session_id: str,
    max_results: int = 5,
) -> list[ContextChunk]:
    """Search the KB for chunks relevant to `query`. Empty list on miss/failure."""
    if not is_configured():
        return []

    body = {"query": query, "max_results": max_results}
    with trace.step(sid := session_id, "senso.search_context", query=query[:120], k=max_results) as ctx:
        try:
            resp = httpx.post(
                f"{SENSO_BASE_URL}/org/search/context",
                headers=_headers(),
                json=body,
                timeout=SENSO_TIMEOUT_S,
            )
            ctx["status"] = resp.status_code
            if resp.status_code >= 400:
                ctx["error"] = resp.text[:300]
                return []
            data = resp.json()
        except (httpx.RequestError, ValueError) as exc:
            ctx["error"] = str(exc)
            return []

    chunks: list[ContextChunk] = []
    # Senso's response shape varies; handle a few common forms.
    raw_results = data.get("results") or data.get("context") or data.get("chunks") or []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        text = (
            item.get("chunk_text")
            or item.get("text")
            or item.get("content")
            or item.get("chunk")
            or item.get("body")
            or ""
        )
        if not text:
            continue
        chunks.append(
            ContextChunk(
                text=text,
                score=float(item.get("score") or item.get("relevance") or 0.0),
                source=str(
                    item.get("title")
                    or item.get("source")
                    or item.get("filename")
                    or item.get("node_id")
                    or ""
                ),
            )
        )

    with trace.step(session_id, "senso.search_context.parsed", returned=len(chunks)):
        pass

    return chunks
