"""End-to-end orchestrator for the demo flow.

A single function `run_pipeline(url)` runs ingest -> match -> draft and
returns a `PipelineResult`. The Streamlit UI is the visible surface, but
this orchestrator is also used by:

  - scripts/demo_precompute.py (caches a full run for DEMO_MODE)
  - scripts/meta_flex.py (runs PaperPilot on its own repo at 16:25)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from paperpilot import trace
from paperpilot.cfp_match import VenueMatch, rank_venues
from paperpilot.clickhouse_client import insert_artifact
from paperpilot.draft import DraftSection, draft_paper
from paperpilot.github_ingest import RepoBundle, fetch_repo
from paperpilot.latex_export import export_paper
from paperpilot.llm_ingest import ResearchSummary, summarize_repo


_log = logging.getLogger(__name__)


def _clickhouse_configured() -> bool:
    return bool(os.environ.get("CLICKHOUSE_HOST"))


def save_artifact(
    user_id: str,
    session_id: str,
    artifact_kind: str,
    artifact_name: str,
    content: str,
    repo: str = "",
    venue: str = "",
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Best-effort: persist a generated artifact to ClickHouse + trace_log.

    user_id is required so the durable artifact row is tenant-scoped and
    the Past Sessions sidebar can filter per user. Returns the sha256
    content_hash on success, None on failure. Never raises.
    """
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    payload = {
        "kind": artifact_kind,
        "name": artifact_name,
        "size_bytes": len(content.encode("utf-8")),
        "content_hash": h,
        "repo": repo,
        "venue": venue,
        **(metadata or {}),
    }
    trace.log_event(session_id, f"artifact.{artifact_kind}.saved", payload)
    if not _clickhouse_configured():
        return h
    try:
        insert_artifact(
            session_id=session_id,
            user_id=user_id,
            artifact_kind=artifact_kind,
            artifact_name=artifact_name,
            content=content,
            repo=repo,
            venue=venue,
            metadata=metadata,
            content_hash=h,
        )
    except Exception as exc:  # noqa: BLE001 -- best-effort; never fail the user
        _log.warning("session_artifacts insert failed: %s", exc)
        trace.log_event(
            session_id,
            f"artifact.{artifact_kind}.save_failed",
            {"error": str(exc), "name": artifact_name},
        )
    return h


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


def stream_full(
    url: str, user_id: str, session_id: str | None = None
) -> Iterator[dict[str, Any]]:
    """High-level generator used by the meta-flex / precompute scripts.

    Yields dict events describing what happened at each stage; useful for
    logging and headless runs. user_id binds the synthesized session to a
    tenant when session_id is not provided.
    """
    sid = session_id or trace.new_session(user_id)
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


def write_demo_cache(url: str, user_id: str = "system") -> Path:
    """Run the pipeline once and serialize for DEMO_MODE.

    user_id defaults to "system" because the demo cache is an admin path
    not tied to any real tenant; pass a real user_id if invoking from a
    user-scoped context.
    """
    sid = trace.new_session(user_id)
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
    # Roll up totals from the trace buffer so demo mode can flash realistic
    # numbers without re-running any LLM call.
    events = trace.buffered_events(sid)
    t_in = sum((e.payload.get("tokens_in") or 0) for e in events if e.kind.endswith(".end"))
    t_out = sum((e.payload.get("tokens_out") or 0) for e in events if e.kind.endswith(".end"))
    cost_usd = sum((e.payload.get("cost_usd") or 0.0) for e in events if e.kind.endswith(".end"))
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
        "totals": {"tokens_in": t_in, "tokens_out": t_out, "cost_usd": cost_usd},
    }
    DEMO_CACHE.write_text(json.dumps(snapshot, indent=2, default=str))
    return DEMO_CACHE


def load_demo_cache() -> dict[str, Any] | None:
    if DEMO_CACHE.exists():
        return json.loads(DEMO_CACHE.read_text())
    return None
