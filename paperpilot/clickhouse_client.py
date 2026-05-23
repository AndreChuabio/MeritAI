"""ClickHouse Cloud client + schema helpers.

Tables:
  - cfp(id, name, scope, deadline, format, scope_emb Array(Float32))
  - arxiv(id, title, abstract, year, authors, emb Array(Float32))
  - trace_log(session_id, ts, kind, payload)

The trace_log is our redundancy against Lapdog missing any subprocess LLM call.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Iterable

import clickhouse_connect
from clickhouse_connect.driver.client import Client


def _normalize_host(raw: str) -> tuple[str, int | None]:
    """Strip protocol prefix and trailing port; return (host, port_or_None).

    ClickHouse Cloud's Connect modal sometimes copies the host as
    `https://xxx.cloud:8443`. The driver wants just the bare host plus a
    numeric port. This handles either format gracefully.
    """
    h = raw.strip()
    for prefix in ("https://", "http://"):
        if h.lower().startswith(prefix):
            h = h[len(prefix) :]
    port: int | None = None
    if ":" in h:
        h, port_str = h.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            port = None
    return h.rstrip("/"), port


def get_client() -> Client:
    """Open a ClickHouse client using env config."""
    host_raw = os.environ["CLICKHOUSE_HOST"]
    host, embedded_port = _normalize_host(host_raw)
    port = embedded_port or int(os.environ.get("CLICKHOUSE_PORT", "8443"))
    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ["CLICKHOUSE_PASSWORD"],
        database=os.environ.get("CLICKHOUSE_DATABASE", "default"),
        secure=os.environ.get("CLICKHOUSE_SECURE", "true").lower() == "true",
    )


# Embedding dimension for openai/text-embedding-3-small.
EMBED_DIM = 1536


SCHEMA_SQL = [
    f"""
    CREATE TABLE IF NOT EXISTS cfp (
        id String,
        name String,
        scope String,
        deadline Date,
        format String,
        url String,
        scope_emb Array(Float32),
        CONSTRAINT scope_emb_len CHECK length(scope_emb) = {EMBED_DIM}
    ) ENGINE = MergeTree() ORDER BY id
    """,
    f"""
    CREATE TABLE IF NOT EXISTS arxiv (
        id String,
        title String,
        abstract String,
        year UInt16,
        authors Array(String),
        emb Array(Float32),
        CONSTRAINT emb_len CHECK length(emb) = {EMBED_DIM}
    ) ENGINE = MergeTree() ORDER BY id
    """,
    """
    CREATE TABLE IF NOT EXISTS trace_log (
        session_id String,
        ts DateTime64(3),
        kind LowCardinality(String),
        payload String
    ) ENGINE = MergeTree() ORDER BY (session_id, ts)
    """,
    """
    CREATE TABLE IF NOT EXISTS user_profile (
        user_id String,
        name String,
        title String,
        about String,
        voice_tone String,
        github_url String,
        linkedin_url String,
        scholar_url String,
        site_url String,
        resume_text String,
        updated_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(updated_at) ORDER BY user_id
    """,
    """
    CREATE TABLE IF NOT EXISTS outreach_log (
        ts DateTime64(3) DEFAULT now64(3),
        user_id String,
        purpose String,
        channel String,
        content_type_id String,
        sample_job_id String,
        draft_id String,
        posted UInt8
    ) ENGINE = MergeTree ORDER BY (ts, user_id)
    """,
]


def init_schema(client: Client | None = None) -> None:
    """Create tables if they do not exist."""
    client = client or get_client()
    for stmt in SCHEMA_SQL:
        client.command(stmt)


def insert_trace(
    session_id: str,
    kind: str,
    payload: dict[str, Any],
    client: Client | None = None,
) -> None:
    """Append a single trace event to trace_log."""
    client = client or get_client()
    client.insert(
        "trace_log",
        [[session_id, datetime.now(), kind, json.dumps(payload, default=str)]],
        column_names=["session_id", "ts", "kind", "payload"],
    )


def fetch_traces(session_id: str, client: Client | None = None) -> list[dict[str, Any]]:
    """Return all trace events for a session in chronological order."""
    client = client or get_client()
    result = client.query(
        "SELECT ts, kind, payload FROM trace_log WHERE session_id = {s:String} ORDER BY ts",
        parameters={"s": session_id},
    )
    return [
        {"ts": r[0], "kind": r[1], "payload": json.loads(r[2])} for r in result.result_rows
    ]


def bulk_insert(table: str, rows: Iterable[list[Any]], column_names: list[str]) -> None:
    """Bulk insert helper used by seed scripts."""
    client = get_client()
    client.insert(table, list(rows), column_names=column_names)
