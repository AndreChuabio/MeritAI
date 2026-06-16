"""Copy the shared corpora (cfp + arxiv) from ClickHouse into Supabase.

One-time migration for the ClickHouse -> Supabase move. Reads the curated CFP
and arxiv rows *with their existing embeddings* out of ClickHouse and upserts
them into Postgres + pgvector, so we pay zero re-embedding cost and preserve
exact vector parity.

Per-user tables (trace_log, session_artifacts, user_profile, outreach_log,
o1_evidence) are intentionally NOT migrated: they hold dev/hackathon data keyed
to string user_ids, while production starts fresh with Supabase-auth UUIDs.

Usage:
    SUPABASE_DB_URL=postgresql://... uv run python scripts/migrate_clickhouse_to_supabase.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paperpilot import clickhouse_client, supabase_client  # noqa: E402


def _read_cfp(ch) -> list[tuple]:
    rows = ch.query(
        "SELECT id, name, scope, deadline, format, url, scope_emb FROM cfp"
    ).result_rows
    return [
        (r[0], r[1], r[2], r[3], r[4], r[5], list(r[6])) for r in rows
    ]


def _read_arxiv(ch) -> list[tuple]:
    rows = ch.query(
        "SELECT id, title, abstract, year, authors, emb FROM arxiv"
    ).result_rows
    return [
        (r[0], r[1], r[2], int(r[3]), list(r[4]), list(r[5])) for r in rows
    ]


def main() -> int:
    load_dotenv()
    if not os.environ.get("SUPABASE_DB_URL"):
        print("SUPABASE_DB_URL is not set. Aborting.", file=sys.stderr)
        return 1

    ch = clickhouse_client.get_client()
    print("Reading corpora from ClickHouse...")
    cfp_rows = _read_cfp(ch)
    arxiv_rows = _read_arxiv(ch)
    print(f"  cfp:   {len(cfp_rows)} rows")
    print(f"  arxiv: {len(arxiv_rows)} rows")

    conn = supabase_client.get_conn()
    try:
        n_cfp = supabase_client.upsert_cfp(cfp_rows, conn=conn)
        n_arxiv = supabase_client.upsert_arxiv(arxiv_rows, conn=conn)
    finally:
        conn.close()

    print("Upserted into Supabase:")
    print(f"  cfp:   {n_cfp}")
    print(f"  arxiv: {n_arxiv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
