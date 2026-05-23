"""One-shot seed of ClickHouse Cloud with CFP + arxiv corpora.

Usage:
    uv run python scripts/seed_clickhouse.py

Idempotent: drops + recreates the cfp and arxiv tables every time. trace_log
is preserved.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from paperpilot.clickhouse_client import EMBED_DIM, get_client, init_schema
from paperpilot.embed import embed_many


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CFP_PATH = ROOT / "data" / "cfp_seed.json"
ARXIV_PATH = ROOT / "data" / "arxiv_seed.json"


def _drop_and_recreate(client, table: str) -> None:
    client.command(f"DROP TABLE IF EXISTS {table}")
    init_schema(client)


def seed_cfp(client) -> int:
    if not CFP_PATH.exists():
        print(f"  ! no cfp_seed.json at {CFP_PATH}")
        return 0
    rows = json.loads(CFP_PATH.read_text())
    print(f"  loading {len(rows)} CFPs from {CFP_PATH.name}...")

    texts = [
        f"{r['name']}: {r['scope']}\nFormat: {r.get('format', '')}" for r in rows
    ]
    print("  embedding scopes...")
    embeddings = embed_many(texts)
    assert all(len(e) == EMBED_DIM for e in embeddings), "embedding dim mismatch"

    _drop_and_recreate(client, "cfp")
    payload = []
    for r, emb in zip(rows, embeddings):
        deadline = datetime.strptime(r["deadline"], "%Y-%m-%d").date()
        payload.append(
            [
                r["id"],
                r["name"],
                r["scope"],
                deadline,
                r.get("format", ""),
                r.get("url", ""),
                emb,
            ]
        )
    client.insert(
        "cfp",
        payload,
        column_names=["id", "name", "scope", "deadline", "format", "url", "scope_emb"],
    )
    return len(payload)


def seed_arxiv(client) -> int:
    if not ARXIV_PATH.exists():
        print(f"  ! no arxiv_seed.json at {ARXIV_PATH} -- skipping (run fetch_arxiv first)")
        return 0
    rows = json.loads(ARXIV_PATH.read_text())
    print(f"  loading {len(rows)} arxiv papers...")
    texts = [f"{r['title']}. {r['abstract']}" for r in rows]
    print("  embedding abstracts...")
    embeddings = embed_many(texts)

    _drop_and_recreate(client, "arxiv")
    payload = []
    for r, emb in zip(rows, embeddings):
        payload.append(
            [r["id"], r["title"], r["abstract"], int(r["year"]), list(r["authors"]), emb]
        )
    client.insert(
        "arxiv",
        payload,
        column_names=["id", "title", "abstract", "year", "authors", "emb"],
    )
    return len(payload)


def main() -> None:
    print(f"[{time.strftime('%H:%M:%S')}] Connecting to ClickHouse Cloud...")
    client = get_client()
    print("  ok")

    print(f"[{time.strftime('%H:%M:%S')}] Ensuring schema...")
    init_schema(client)

    print(f"[{time.strftime('%H:%M:%S')}] Seeding cfp...")
    n_cfp = seed_cfp(client)
    print(f"  inserted {n_cfp} CFPs")

    print(f"[{time.strftime('%H:%M:%S')}] Seeding arxiv...")
    n_arx = seed_arxiv(client)
    print(f"  inserted {n_arx} arxiv papers")

    print(f"[{time.strftime('%H:%M:%S')}] Done.")


if __name__ == "__main__":
    main()
