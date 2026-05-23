"""End-to-end orchestrator for the demo flow.

A single function `run_pipeline(url)` runs ingest -> match -> draft and
returns a `PipelineResult`. The Streamlit UI is the visible surface, but
this orchestrator is also used by:

  - scripts/demo_precompute.py (caches a full run for DEMO_MODE)
  - scripts/meta_flex.py (runs PaperPilot on its own repo at 16:25)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator

from paperpilot import trace
from paperpilot.cfp_match import VenueMatch, rank_venues
from paperpilot.draft import DraftSection, draft_paper
from paperpilot.github_ingest import RepoBundle, fetch_repo
from paperpilot.latex_export import export_paper
from paperpilot.llm_ingest import ResearchSummary, summarize_repo


DEMO_CACHE = Path(__file__).resolve().parent.parent / "data" / "demo_cache.json"


@dataclass
class PipelineResult:
    session_id: str
    bundle: RepoBundle
    summary: ResearchSummary
    venues: list[VenueMatch]
    chosen: VenueMatch | None
    sections: dict[str, DraftSection]
    tex: str
    bib: str


def _is_demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "").lower() == "true"


def ingest_and_match(url: str, session_id: str) -> tuple[RepoBundle, ResearchSummary, list[VenueMatch]]:
    """Stage 1 + 2: pull the repo, summarize, rank venues."""
    bundle = fetch_repo(url)
    trace.log_event(
        session_id,
        "ingest.github",
        {"repo": f"{bundle.owner}/{bundle.name}", "files": bundle.file_count, "tokens": bundle.total_tokens},
    )
    summary = summarize_repo(bundle, session_id)
    venues = rank_venues(summary, session_id, limit=5)
    return bundle, summary, venues


def draft_for(
    summary: ResearchSummary, venue: VenueMatch, session_id: str
) -> Iterator[tuple[str, str]]:
    """Stage 3: stream the paper sections. Yields (section, delta)."""
    yield from draft_paper(summary, venue, session_id)


def stream_full(url: str, session_id: str | None = None) -> Iterator[dict[str, Any]]:
    """High-level generator used by the meta-flex / precompute scripts.

    Yields dict events describing what happened at each stage; useful for
    logging and headless runs.
    """
    sid = session_id or trace.new_session()
    bundle, summary, venues = ingest_and_match(url, sid)
    yield {"stage": "ingest", "summary": summary.model_dump()}
    yield {"stage": "match", "venues": [v.__dict__ for v in venues]}
    if not venues:
        return
    venue = venues[0]
    sections: dict[str, DraftSection] = {}
    gen = draft_paper(summary, venue, sid)
    try:
        while True:
            section, delta = next(gen)
            yield {"stage": "draft", "section": section, "delta": delta}
    except StopIteration as stop:
        sections = stop.value
    tex, bib = export_paper(summary, venue, sections)
    yield {"stage": "export", "tex_len": len(tex), "bib_len": len(bib)}


def write_demo_cache(url: str) -> Path:
    """Run the pipeline once and serialize for DEMO_MODE."""
    sid = trace.new_session()
    bundle, summary, venues = ingest_and_match(url, sid)
    if not venues:
        raise RuntimeError(
            "No CFPs matched within the deadline horizon. "
            "Check data/cfp_seed.json deadlines or widen the horizon_days."
        )
    venue = venues[0]
    sections: dict[str, DraftSection] = {}
    gen = draft_paper(summary, venue, sid)
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        sections = stop.value
    tex, bib = export_paper(summary, venue, sections)
    snapshot = {
        "session_id": sid,
        "url": url,
        "repo": f"{bundle.owner}/{bundle.name}",
        "summary": summary.model_dump(),
        "venues": [v.__dict__ for v in venues],
        "chosen": venue.__dict__,
        "sections": {
            k: {
                "text": s.text,
                "citations": [c.__dict__ for c in s.citations],
                "stripped_ids": s.stripped_ids,
            }
            for k, s in sections.items()
        },
        "tex": tex,
        "bib": bib,
    }
    DEMO_CACHE.write_text(json.dumps(snapshot, indent=2, default=str))
    return DEMO_CACHE


def load_demo_cache() -> dict[str, Any] | None:
    if DEMO_CACHE.exists():
        return json.loads(DEMO_CACHE.read_text())
    return None
