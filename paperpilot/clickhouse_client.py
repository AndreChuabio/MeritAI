"""ClickHouse Cloud client + schema helpers.

Tables:
  - cfp(id, name, scope, deadline, format, scope_emb Array(Float32))
  - arxiv(id, title, abstract, year, authors, emb Array(Float32))
  - trace_log(session_id, ts, kind, payload)
  - session_artifacts(session_id, ts, artifact_kind, repo, venue,
                      artifact_name, size_bytes, content_hash,
                      content, metadata)

trace_log is our redundancy against Lapdog missing any subprocess LLM call;
session_artifacts is the durable record of every paper/plugin shipped out
of the UI, tagged to session so judges can replay any prior run.
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
    CREATE TABLE IF NOT EXISTS session_artifacts (
        session_id String,
        ts DateTime64(3),
        artifact_kind LowCardinality(String),
        repo String,
        venue String,
        artifact_name String,
        size_bytes UInt32,
        content_hash String,
        content String,
        metadata String
    ) ENGINE = MergeTree() ORDER BY (session_id, ts)
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


def insert_artifact(
    session_id: str,
    artifact_kind: str,
    artifact_name: str,
    content: str,
    repo: str = "",
    venue: str = "",
    metadata: dict[str, Any] | None = None,
    content_hash: str = "",
    client: Client | None = None,
) -> None:
    """Append a single generated artifact (paper, plugin, etc.) to session_artifacts.

    Best-effort: caller layer wraps in try/except so a ClickHouse outage
    never blocks the user's download.
    """
    client = client or get_client()
    size = len(content.encode("utf-8"))
    client.insert(
        "session_artifacts",
        [
            [
                session_id,
                datetime.now(),
                artifact_kind,
                repo,
                venue,
                artifact_name,
                size,
                content_hash,
                content,
                json.dumps(metadata or {}, default=str),
            ]
        ],
        column_names=[
            "session_id",
            "ts",
            "artifact_kind",
            "repo",
            "venue",
            "artifact_name",
            "size_bytes",
            "content_hash",
            "content",
            "metadata",
        ],
    )


def fetch_artifacts(
    session_id: str | None = None,
    artifact_kind: str | None = None,
    limit: int = 50,
    client: Client | None = None,
) -> list[dict[str, Any]]:
    """Return artifact rows (newest first). Filters optional.

    For the sidebar we typically call with session_id=None to show every
    run this ClickHouse instance has persisted.
    """
    client = client or get_client()
    where_parts: list[str] = []
    params: dict[str, Any] = {"lim": limit}
    if session_id is not None:
        where_parts.append("session_id = {sid:String}")
        params["sid"] = session_id
    if artifact_kind is not None:
        where_parts.append("artifact_kind = {kind:String}")
        params["kind"] = artifact_kind
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    sql = (
        "SELECT session_id, ts, artifact_kind, repo, venue, artifact_name, "
        "size_bytes, content_hash, metadata "
        f"FROM session_artifacts {where} "
        "ORDER BY ts DESC LIMIT {lim:UInt32}"
    )
    result = client.query(sql, parameters=params)
    rows: list[dict[str, Any]] = []
    for r in result.result_rows:
        rows.append(
            {
                "session_id": r[0],
                "ts": r[1],
                "artifact_kind": r[2],
                "repo": r[3],
                "venue": r[4],
                "artifact_name": r[5],
                "size_bytes": r[6],
                "content_hash": r[7],
                "metadata": json.loads(r[8]) if r[8] else {},
            }
        )
    return rows


def fetch_artifact_content(
    session_id: str,
    artifact_name: str,
    client: Client | None = None,
) -> str | None:
    """Pull the raw content blob for one specific artifact (newest match)."""
    client = client or get_client()
    result = client.query(
        "SELECT content FROM session_artifacts "
        "WHERE session_id = {sid:String} AND artifact_name = {an:String} "
        "ORDER BY ts DESC LIMIT 1",
        parameters={"sid": session_id, "an": artifact_name},
    )
    if not result.result_rows:
        return None
    return result.result_rows[0][0]
