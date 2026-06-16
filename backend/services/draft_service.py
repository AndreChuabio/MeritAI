"""Draft service: stream a paper draft section-by-section over Supabase.

The legacy `paperpilot.draft.draft_paper` orchestrator sources its arxiv
citation candidates from ClickHouse via
`arxiv_lookup.candidates_from_clickhouse`. The FastAPI backend talks to
Supabase instead, so this module replaces only the candidate pre-filter:
it embeds the repo summary and pulls the closest arxiv rows from
`supabase_client.match_arxiv`, adapting each row into the `PaperMeta` shape
that `draft.draft_section` already understands.

Everything else -- the section prompts, Senso tone injection, streaming,
and the post-hoc citation gate -- is reused unchanged from
`paperpilot.draft`. The adapter also seeds `arxiv_lookup._CACHE` so the
post-draft citation enrichment never hits the flaky external arxiv API for
an ID we already pulled from Supabase.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Generator

from paperpilot import arxiv_lookup, supabase_client
from paperpilot.arxiv_lookup import PaperMeta
from paperpilot.cfp_match import VenueMatch
from paperpilot.draft import SECTIONS, DraftSection, draft_section
from paperpilot.embed import embed_one
from paperpilot.llm_ingest import ResearchSummary


def _summary_text(summary: ResearchSummary) -> str:
    """Build the embedding query text for arxiv candidate retrieval.

    Mirrors the text `draft.draft_paper` feeds to the ClickHouse pre-filter
    so Supabase candidates rank against the same signal.
    """
    return (
        f"{summary.problem} {summary.contribution} {summary.method} "
        f"Keywords: {', '.join(summary.keywords)}"
    )


def candidates_from_supabase(
    summary: ResearchSummary, limit: int = 10
) -> list[PaperMeta]:
    """Pre-filter arxiv citation candidates from Supabase pgvector.

    Supabase counterpart to `arxiv_lookup.candidates_from_clickhouse`.
    Embeds the summary, queries `match_arxiv`, and adapts each row into a
    `PaperMeta`. Adapted rows are written into `arxiv_lookup._CACHE` so the
    citation-enrichment pass in `draft.draft_section` resolves them from
    cache instead of the live arxiv API.
    """
    q_emb = embed_one(_summary_text(summary))
    rows = supabase_client.match_arxiv(q_emb, limit=limit)
    candidates: list[PaperMeta] = []
    for pid, title, abstract, year, authors in rows:
        meta = PaperMeta(
            id=pid,
            title=title,
            authors=list(authors or []),
            year=int(year) if year is not None else 0,
            abstract=abstract or "",
        )
        arxiv_lookup._CACHE[pid] = meta
        candidates.append(meta)
    return candidates


def _venue_from_payload(venue: dict[str, Any]) -> VenueMatch:
    """Adapt the request's venue dict into the VenueMatch the drafter needs.

    Only `name` and `scope` are read by the section prompts; the remaining
    fields are filled with neutral defaults so the dataclass is well-formed.
    """
    deadline_raw = venue.get("deadline")
    deadline: date
    if isinstance(deadline_raw, date):
        deadline = deadline_raw
    elif isinstance(deadline_raw, str) and deadline_raw:
        try:
            deadline = date.fromisoformat(deadline_raw[:10])
        except ValueError:
            deadline = date.today()
    else:
        deadline = date.today()

    return VenueMatch(
        id=str(venue.get("id", "")),
        name=str(venue.get("name", "")),
        scope=str(venue.get("scope", "")),
        deadline=deadline,
        url=str(venue.get("url", "")),
        fit_score=float(venue.get("fit_score", 0.0)),
        days_until_deadline=int(venue.get("days_until_deadline", 0)),
    )


def draft_paper_supabase(
    summary: ResearchSummary,
    venue: dict[str, Any],
    session_id: str,
    candidate_limit: int = 10,
) -> Generator[tuple[str, str], None, dict[str, DraftSection]]:
    """Stream every section in order, yielding (section_name, delta) tuples.

    Supabase counterpart to `draft.draft_paper`. Sources arxiv candidates
    from Supabase, then delegates each section to the unchanged
    `draft.draft_section`. Returns the assembled section map at the end.
    """
    venue_match = _venue_from_payload(venue)
    candidates = candidates_from_supabase(summary, limit=candidate_limit)

    out: dict[str, DraftSection] = {}
    for section in SECTIONS:
        gen = draft_section(
            section,
            summary,
            venue_match,
            session_id,
            candidates if section == "related" else None,
        )
        try:
            while True:
                yield section, next(gen)
        except StopIteration as stop:
            out[section] = stop.value
    return out
