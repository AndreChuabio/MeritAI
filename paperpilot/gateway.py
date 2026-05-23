"""Vercel AI Gateway client.

Uses the OpenAI-compatible endpoint so we can route to Anthropic, Google, and
OpenAI providers from a single client. Provider/model is encoded in the model
string: e.g. "anthropic/claude-sonnet-4-6", "google/gemini-2.5-flash",
"openai/text-embedding-3-small".

Lapdog intercepts these calls when the process is wrapped via
`lapdog python ...` or `lapdog streamlit run ...`.
"""

from __future__ import annotations

import os

from openai import OpenAI


GATEWAY_BASE_URL = os.environ.get(
    "AI_GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh/v1"
)


def get_client() -> OpenAI:
    """Return an OpenAI client pointed at Vercel AI Gateway."""
    api_key = os.environ.get("AI_GATEWAY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "AI_GATEWAY_API_KEY missing. Get one at "
            "https://vercel.com/dashboard/ai-gateway and add to .env"
        )
    return OpenAI(base_url=GATEWAY_BASE_URL, api_key=api_key)


DEFAULTS = {
    "ingest": os.environ.get("MODEL_INGEST", "google/gemini-2.5-flash"),
    "draft": os.environ.get("MODEL_DRAFT", "anthropic/claude-sonnet-4-6"),
    "embed": os.environ.get("MODEL_EMBED", "openai/text-embedding-3-small"),
}
