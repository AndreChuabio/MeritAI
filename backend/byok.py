"""Bring-your-own-key: bind the caller's gateway key to this request.

Merit never stores a user's API key. The browser holds it, sends it on each
request in the X-LLM-Key header, and this dependency binds it to the request
context for the duration of the call. Nothing writes it to a table, a log, or a
response body. See backend/logging_filters.py for the scrubbing that enforces
the log half of that promise.

The key is a Vercel AI Gateway key, not a provider key: Merit calls Google for
ingest, Anthropic for drafting, and OpenAI for embeddings, so no single provider
key can run the pipeline.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from paperpilot import gateway


async def require_llm_key(
    x_llm_key: str | None = Header(default=None),
) -> None:
    """FastAPI dependency: bind the caller's gateway key, or reject the request."""
    if not x_llm_key or not x_llm_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This surface runs on your own API key. Supply a Vercel AI "
                "Gateway key in the X-LLM-Key header."
            ),
        )
    gateway.set_request_key(x_llm_key.strip())


RequireLLMKey = Depends(require_llm_key)
