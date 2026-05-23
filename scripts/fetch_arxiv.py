"""Fetch a curated arxiv corpus for citation grounding.

Queries arxiv across topic clusters that match common CFP scopes, dedupes,
and writes data/arxiv_seed.json. Runs once before seed_clickhouse.

Usage:
    uv run python scripts/fetch_arxiv.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import arxiv


# Each query yields ~25 papers across the listed categories.
QUERIES = [
    # Foundation models / LLMs
    ("foundation models large language models", 25),
    ("retrieval augmented generation", 20),
    ("tool use agents llm", 20),
    ("instruction tuning rlhf", 15),
    # Observability / evaluation
    ("llm observability evaluation benchmark", 15),
    ("hallucination detection llm", 15),
    # Clinical ML
    ("clinical natural language processing", 20),
    ("clinical decision support deep learning", 15),
    ("electronic health records machine learning", 15),
    ("medical imaging deep learning", 15),
    # ML systems
    ("vector databases embeddings", 10),
    ("efficient inference llm serving", 15),
    # Agentic
    ("agent multi-step reasoning", 15),
    ("code generation language model", 15),
]


OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "arxiv_seed.json"


_ARXIV_CLIENT = arxiv.Client(page_size=50, delay_seconds=3.0, num_retries=3)


def fetch_one(query: str, max_results: int) -> list[dict]:
    print(f"  query: {query!r} (n={max_results})")
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )
    out: list[dict] = []
    for result in _ARXIV_CLIENT.results(search):
        # Strip the version suffix from the arxiv id (we want the canonical id).
        aid = result.entry_id.rsplit("/", 1)[-1].split("v")[0]
        out.append(
            {
                "id": aid,
                "title": result.title.strip(),
                "abstract": result.summary.replace("\n", " ").strip(),
                "year": int(result.published.year) if result.published else 0,
                "authors": [a.name for a in result.authors],
                "categories": list(result.categories),
            }
        )
    return out


def main() -> None:
    all_rows: dict[str, dict] = {}
    for query, n in QUERIES:
        try:
            rows = fetch_one(query, n)
        except Exception as exc:  # noqa: BLE001
            print(f"    !! failed: {exc}")
            continue
        for r in rows:
            all_rows.setdefault(r["id"], r)
        # arxiv.Client already throttles via delay_seconds; small extra pause
        # between distinct queries keeps us well under the rate limit.
        time.sleep(1.0)

    deduped = list(all_rows.values())
    deduped.sort(key=lambda r: r["year"], reverse=True)
    OUT_PATH.write_text(json.dumps(deduped, indent=2))
    print(f"\nWrote {len(deduped)} unique papers to {OUT_PATH}")


if __name__ == "__main__":
    main()
