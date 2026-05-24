"""One-shot refresh of the cfp ClickHouse corpus with live Nimble web data.

Run before the demo to enrich the 41 hand-curated venues in `cfp_seed.json`
with up-to-20 fresh CFPs that Nimble discovers on the live web. Skip
silently if NIMBLE_API_KEY is unset.

This is the production-shaped variant of what `_nimble_candidate_venues`
does at query time. The query-time path stays as a "freshness check" —
this script gives the corpus a periodic baseline refresh.

Usage:
    uv run python scripts/refresh_cfp_corpus.py
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from paperpilot import nimble_client  # noqa: E402
from paperpilot.cfp_match import _parse_deadline  # noqa: E402  (reuse the regex)
from paperpilot.clickhouse_client import get_client  # noqa: E402
from paperpilot.embed import embed_many  # noqa: E402
from paperpilot.trace import new_session  # noqa: E402


load_dotenv()


# Short, focused queries -- Nimble Search is slow on broad terms.
QUERIES = [
    "ML4H 2026 call for papers",
    "NeurIPS 2026 workshops deadline",
    "clinical NLP workshop 2026",
    "LLM agents conference 2026",
]

MAX_NEW_VENUES = 20
EXTRACT_BODY_CAP = 1500  # chars from Extract body to use as scope


@dataclass
class Candidate:
    cfp_id: str
    name: str
    scope: str
    url: str
    deadline: date


def _is_conference_url(url: str) -> bool:
    """Cheap heuristic: drop social-media + clearly non-conference URLs."""
    bad_substrings = (
        "twitter.com",
        "x.com/",
        "facebook.com",
        "linkedin.com",
        "reddit.com",
        "youtube.com",
        "amazon.com",
        "/login",
        "/signup",
    )
    u = url.lower()
    return not any(b in u for b in bad_substrings)


def _venue_id(url: str) -> str:
    """Deterministic ID so re-running this script is idempotent (ReplacingMergeTree
    semantics would be cleaner, but our table is MergeTree -- so we keep an
    in-memory dedupe set instead and skip rows whose id already exists)."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"nimble:{h}"


def _existing_ids(client) -> set[str]:
    r = client.query("SELECT id FROM cfp WHERE startsWith(id, 'nimble:')")
    return {row[0] for row in r.result_rows}


def main() -> None:
    if not nimble_client.is_configured():
        print("NIMBLE_API_KEY not set. Skipping corpus refresh.")
        sys.exit(0)
    sid = new_session("system")
    print(f"Session: {sid}")

    client = get_client()
    existing = _existing_ids(client)
    print(f"Existing nimble:* venues in cfp: {len(existing)}")

    seen: dict[str, dict] = {}
    for q in QUERIES:
        print(f"  search: {q[:70]}")
        hits = nimble_client.search(q, sid, k=8)
        if not hits:
            print("    no hits")
            continue
        for h in hits:
            if not h.url or not _is_conference_url(h.url):
                continue
            seen.setdefault(h.url, {"hit": h})

    print(f"Unique conference-shaped URLs: {len(seen)}")

    candidates: list[Candidate] = []
    for url, entry in seen.items():
        if len(candidates) >= MAX_NEW_VENUES:
            break
        h = entry["hit"]
        cfp_id = _venue_id(url)
        if cfp_id in existing:
            continue
        # Best-effort Extract for richer scope + deadline parsing.
        extract = nimble_client.extract(url, sid)
        body = ""
        if extract and isinstance(extract, dict):
            body = (
                extract.get("body")
                or extract.get("text")
                or extract.get("content")
                or ""
            )
        deadline_text = body[:4000] or (h.title + " " + h.snippet)
        deadline, _days = _parse_deadline(deadline_text, default_days_out=90)
        # Skip venues whose parseable deadline is in the past (likely stale results).
        if deadline < date.today():
            continue
        scope_text = (body[:EXTRACT_BODY_CAP] or h.snippet[:500] or h.title).strip()
        if not scope_text or len(scope_text) < 40:
            continue
        candidates.append(
            Candidate(
                cfp_id=cfp_id,
                name=h.title[:200] or url,
                scope=scope_text,
                url=url,
                deadline=deadline,
            )
        )
        print(f"  + {h.title[:80]}  (deadline={deadline}, scope={len(scope_text)} chars)")

    if not candidates:
        print("No new venues to insert.")
        return

    print(f"Embedding {len(candidates)} scopes...")
    embeddings = embed_many([c.scope for c in candidates])

    print("Inserting into cfp...")
    rows = []
    for c, emb in zip(candidates, embeddings):
        rows.append(
            [c.cfp_id, c.name, c.scope, c.deadline, "", c.url, list(emb)]
        )
    client.insert(
        "cfp",
        rows,
        column_names=["id", "name", "scope", "deadline", "format", "url", "scope_emb"],
    )
    print(f"Inserted {len(rows)} new nimble:* rows.")
    # Final tally.
    total = client.query("SELECT count() FROM cfp").result_rows[0][0]
    nimble = client.query(
        "SELECT count() FROM cfp WHERE startsWith(id, 'nimble:')"
    ).result_rows[0][0]
    print(f"cfp total: {total}  (nimble-discovered: {nimble})")


if __name__ == "__main__":
    main()
