"""arxiv citation grounding.

Two layers of defense against citation hallucination:

  1. Candidate pre-filter via ClickHouse: pull the top-N arxiv IDs whose
     embeddings are closest to the repo summary. These are the only IDs
     the drafter is allowed to cite.
  2. Tool gate: when drafting related work, the LLM must call
     `lookup_paper(arxiv_id)` to read each candidate before citing.

Both layers are belt-and-suspenders; either alone would catch most cases.
"""

from __future__ import annotations

from dataclasses import dataclass

import arxiv

from paperpilot import trace
from paperpilot.clickhouse_client import get_client
from paperpilot.embed import embed_one


@dataclass
class PaperMeta:
    id: str
    title: str
    authors: list[str]
    year: int
    abstract: str


_CACHE: dict[str, PaperMeta] = {}


def candidates_from_clickhouse(
    summary_text: str, session_id: str, limit: int = 10
) -> list[PaperMeta]:
    """Pre-filter arxiv candidates by semantic similarity to the repo summary."""
    with trace.step(session_id, "citation.candidates", limit=limit) as ctx:
        q_emb = embed_one(summary_text)
        client = get_client()
        result = client.query(
            """
            SELECT id, title, abstract, year, authors
            FROM arxiv
            ORDER BY cosineDistance(emb, {q:Array(Float32)}) ASC
            LIMIT {n:UInt32}
            """,
            parameters={"q": q_emb, "n": limit},
        )
        ctx["rows"] = len(result.result_rows)
    candidates: list[PaperMeta] = []
    for row in result.result_rows:
        pid, title, abstract, year, authors = row
        meta = PaperMeta(
            id=pid, title=title, authors=list(authors), year=int(year), abstract=abstract
        )
        _CACHE[pid] = meta
        candidates.append(meta)
    return candidates


def lookup_paper(arxiv_id: str) -> PaperMeta | None:
    """Tool exposed to the drafter. Hits cache first, then live arxiv."""
    if arxiv_id in _CACHE:
        return _CACHE[arxiv_id]
    try:
        search = arxiv.Search(id_list=[arxiv_id])
        result = next(search.results(), None)
    except Exception:  # noqa: BLE001 -- arxiv lib is flaky over conf wifi
        return None
    if result is None:
        return None
    year = int(result.published.year) if result.published else 0
    meta = PaperMeta(
        id=arxiv_id,
        title=result.title.strip(),
        authors=[a.name for a in result.authors],
        year=year,
        abstract=result.summary.replace("\n", " ").strip(),
    )
    _CACHE[arxiv_id] = meta
    return meta


def bibtex_for(meta: PaperMeta) -> str:
    """Produce a minimal BibTeX entry for the paper."""
    key = f"{meta.authors[0].split()[-1].lower() if meta.authors else 'anon'}{meta.year}"
    authors = " and ".join(meta.authors)
    return (
        f"@article{{{key}_{meta.id.replace('.', '_')},\n"
        f"  title={{ {meta.title} }},\n"
        f"  author={{ {authors} }},\n"
        f"  year={{ {meta.year} }},\n"
        f"  journal={{ arXiv:{meta.id} }}\n"
        f"}}\n"
    )
