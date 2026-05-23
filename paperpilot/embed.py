"""Embedding helper.

Wraps OpenAI text-embedding-3-small through Vercel AI Gateway. 1536-dim
vectors, matched to the `EMBED_DIM` constant in clickhouse_client.
"""

from __future__ import annotations

from typing import Iterable

from paperpilot.gateway import DEFAULTS, get_client


_MAX_BATCH = 64


def embed_one(text: str) -> list[float]:
    """Embed a single string."""
    client = get_client()
    resp = client.embeddings.create(model=DEFAULTS["embed"], input=text)
    return list(resp.data[0].embedding)


def embed_many(texts: Iterable[str]) -> list[list[float]]:
    """Embed a batch of strings. Splits into chunks of _MAX_BATCH."""
    client = get_client()
    texts = list(texts)
    out: list[list[float]] = []
    for i in range(0, len(texts), _MAX_BATCH):
        batch = texts[i : i + _MAX_BATCH]
        resp = client.embeddings.create(model=DEFAULTS["embed"], input=batch)
        out.extend([list(d.embedding) for d in resp.data])
    return out
