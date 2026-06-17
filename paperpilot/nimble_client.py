"""Nimble web-data client.

Wraps three Nimble SDK endpoints we actually use in Merit:

  - Search:  POST /v1/search   {query}                                 -> {results, ...}
  - Answers: POST /v1/search   {query, include_answer: true, ...}      -> {answer, results, ...}
  - Extract: POST /v1/extract  {url, render, parse}                    -> {data, ...}

Every call is wrapped by `trace.step` so it shows up in the agent trace
panel and the Datadog cloud forward. Calls have a hard timeout so a slow
Nimble cannot break the paper draft or plugin extractor flow. Missing
NIMBLE_API_KEY returns None with a logged event -- never raises.

Auth: Bearer NIMBLE_API_KEY.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from paperpilot import trace


_log = logging.getLogger(__name__)

NIMBLE_BASE_URL = os.environ.get("NIMBLE_BASE_URL", "https://sdk.nimbleway.com")
NIMBLE_TIMEOUT_S = float(os.environ.get("NIMBLE_TIMEOUT_S", "8.0"))


def _api_key() -> str | None:
    return os.environ.get("NIMBLE_API_KEY") or None


def is_configured() -> bool:
    return _api_key() is not None


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def search(query: str, session_id: str, k: int = 5) -> list[SearchHit] | None:
    """Nimble Search: POST /v1/search.

    Returns the top-k hits as SearchHit list. Returns None on misconfig,
    timeout, or non-2xx -- callers should treat None as "skip the panel."
    """
    if not is_configured():
        return None
    payload = {"query": query}
    with trace.step(session_id, "nimble.search", query=query[:80], k=k) as ctx:
        try:
            r = httpx.post(
                f"{NIMBLE_BASE_URL}/v1/search",
                headers=_headers(),
                json=payload,
                timeout=NIMBLE_TIMEOUT_S,
            )
            r.raise_for_status()
            data = r.json()
            ctx["total_results"] = data.get("total_results")
            ctx["request_id"] = data.get("request_id")
            hits_raw = data.get("results") or []
            hits = [
                SearchHit(
                    title=str(h.get("title", "")),
                    url=str(h.get("url", "")),
                    snippet=str(h.get("snippet") or h.get("description") or ""),
                )
                for h in hits_raw[:k]
            ]
            ctx["returned"] = len(hits)
            return hits
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            ctx["error"] = str(exc)
            _log.warning("nimble.search failed: %s", exc)
            return None


def answers(query: str, session_id: str, depth: str = "lite") -> dict[str, Any] | None:
    """Nimble Answers: POST /v1/search with include_answer=true.

    Returns {"answer": str, "citations": [SearchHit-like], "request_id"} or None.
    """
    if not is_configured():
        return None
    payload = {"query": query, "search_depth": depth, "include_answer": True}
    with trace.step(session_id, "nimble.answers", query=query[:80], depth=depth) as ctx:
        try:
            r = httpx.post(
                f"{NIMBLE_BASE_URL}/v1/search",
                headers=_headers(),
                json=payload,
                timeout=NIMBLE_TIMEOUT_S * 2,  # answers do more work; give extra
            )
            r.raise_for_status()
            data = r.json()
            ans = data.get("answer") or ""
            results = data.get("results") or []
            ctx["answer_chars"] = len(ans)
            ctx["citations"] = len(results)
            ctx["request_id"] = data.get("request_id")
            return {
                "answer": ans,
                "citations": [
                    {
                        "title": str(h.get("title", "")),
                        "url": str(h.get("url", "")),
                        "snippet": str(h.get("snippet") or h.get("description") or ""),
                    }
                    for h in results[:5]
                ],
                "request_id": data.get("request_id"),
            }
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            ctx["error"] = str(exc)
            _log.warning("nimble.answers failed: %s", exc)
            return None


def extract(url: str, session_id: str, parser: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Nimble Extract: POST /v1/extract for structured data from a URL.

    If `parser` is provided, asks Nimble to parse with the schema. Otherwise
    returns the rendered page payload. Returns the response dict or None.
    """
    if not is_configured():
        return None
    payload: dict[str, Any] = {"url": url, "render": True}
    if parser is not None:
        payload["parse"] = True
        payload["parser"] = parser
    with trace.step(session_id, "nimble.extract", url=url[:120]) as ctx:
        try:
            r = httpx.post(
                f"{NIMBLE_BASE_URL}/v1/extract",
                headers=_headers(),
                json=payload,
                timeout=NIMBLE_TIMEOUT_S * 2,
            )
            r.raise_for_status()
            data = r.json()
            ctx["status_code"] = data.get("status_code")
            ctx["status"] = data.get("status")
            ctx["task_id"] = data.get("task_id")
            ctx["fields"] = list((data.get("data") or {}).keys())[:8]
            return data
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            ctx["error"] = str(exc)
            _log.warning("nimble.extract failed: %s", exc)
            return None
