"""Ingest service: GitHub repo -> structured ResearchSummary.

Thin orchestration layer over the existing paperpilot ingestion pipeline.
We reuse github_ingest.fetch_repo to assemble a token-capped bundle and
llm_ingest.summarize_repo to produce the structured summary. The backend
contributes only the session id, auth scoping, and a best-effort Supabase
trace write so the run is durable per tenant.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from paperpilot import supabase_client
from paperpilot.github_ingest import fetch_repo
from paperpilot.llm_ingest import ResearchSummary, summarize_repo

_log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Outcome of an ingest run: the summary plus repo and session metadata."""

    session_id: str
    owner: str
    name: str
    file_count: int
    summary: ResearchSummary


def _new_session_id() -> str:
    """Generate a session id grouping this end-to-end ingest run."""
    return f"sess_{uuid.uuid4().hex[:12]}"


def ingest_repo(repo_url: str, user_id: str) -> IngestResult:
    """Fetch a GitHub repo and summarize it into a ResearchSummary.

    The repo is bundled via github_ingest.fetch_repo and summarized via
    llm_ingest.summarize_repo. A new session id is generated for the run and
    an ingest trace is written best-effort to Supabase; a trace failure is
    logged and swallowed so it never breaks the response.
    """
    session_id = _new_session_id()
    bundle = fetch_repo(repo_url)
    summary = summarize_repo(bundle, session_id)

    payload = {
        "repo_url": repo_url,
        "owner": bundle.owner,
        "name": bundle.name,
        "file_count": bundle.file_count,
        "repo_tokens": bundle.total_tokens,
        "keywords": summary.keywords,
        "venue_hints": summary.venue_hints,
    }
    try:
        supabase_client.insert_trace(session_id, user_id, "ingest", payload)
    except Exception as exc:  # noqa: BLE001 -- best-effort; never break the response
        _log.warning("ingest trace insert failed for session %s: %s", session_id, exc)

    return IngestResult(
        session_id=session_id,
        owner=bundle.owner,
        name=bundle.name,
        file_count=bundle.file_count,
        summary=summary,
    )
