"""Ingest service: GitHub repo -> structured ResearchSummary.

Thin orchestration layer over the existing paperpilot ingestion pipeline.
We reuse github_ingest.fetch_repo to assemble a token-capped bundle and
llm_ingest.summarize_repo to produce the structured summary. The backend
contributes only the session id, auth scoping, and a best-effort Supabase
trace write so the run is durable per tenant.

The rendered bundle is also persisted as a "repo_bundle" artifact keyed by
session_id so a later /extract-plugin call in the same session can reuse it
instead of re-fetching the repo and re-assembling the bundle from scratch --
see backend/services/plugin_service.py's _load_bundle.

Runs on the user's own API key (BYOK), so bundle size is also a cost the
ingest_repo caller opts into: past MAX_UNCONFIRMED_TOKENS estimated tokens,
check_bundle_size refuses until the caller confirms explicitly.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status

from paperpilot import supabase_client
from paperpilot.github_ingest import fetch_repo, render_bundle
from paperpilot.llm_ingest import ResearchSummary, summarize_repo

_log = logging.getLogger(__name__)

# Above this estimated token count, the caller is told what the run will
# cost them on their own key and must opt in explicitly. The bundle can
# reach 600K tokens (paperpilot/github_ingest.py DEFAULT_TOKEN_CAP) -- real
# money on a BYOK run, so it should be spent deliberately, not by accident.
MAX_UNCONFIRMED_TOKENS = int(os.environ.get("MAX_UNCONFIRMED_TOKENS", "150000"))


def check_bundle_size(estimated_tokens: int, confirm_large: bool) -> None:
    """Refuse an oversized ingest until the caller has confirmed it.

    Reads MAX_UNCONFIRMED_TOKENS from the module namespace (not a captured
    default) so tests -- and any future runtime reconfiguration -- can
    override it.
    """
    if confirm_large or estimated_tokens <= MAX_UNCONFIRMED_TOKENS:
        return
    raise HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=(
            f"This repository bundles to roughly {estimated_tokens:,} tokens, "
            f"above the {MAX_UNCONFIRMED_TOKENS:,}-token threshold. It runs on "
            "your own API key. Re-send with confirm_large=true to proceed."
        ),
    )


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


def ingest_repo(repo_url: str, user_id: str, confirm_large: bool = False) -> IngestResult:
    """Fetch a GitHub repo and summarize it into a ResearchSummary.

    The repo is bundled via github_ingest.fetch_repo and summarized via
    llm_ingest.summarize_repo. A new session id is generated for the run and
    an ingest trace is written best-effort to Supabase; a trace failure is
    logged and swallowed so it never breaks the response.

    Before spending anything, check_bundle_size raises HTTPException(413) if
    the bundle is oversized and confirm_large was not set -- the caller must
    re-send with confirm_large=True to proceed, since this runs on their key.

    The rendered bundle is then persisted as a "repo_bundle" artifact (also
    best-effort) so /extract-plugin can reuse it instead of paying to fetch
    and re-render the same repo a second time.
    """
    session_id = _new_session_id()
    bundle = fetch_repo(repo_url)
    check_bundle_size(estimated_tokens=bundle.total_tokens, confirm_large=confirm_large)

    rendered = render_bundle(bundle)
    try:
        supabase_client.insert_artifact(
            session_id,
            user_id,
            "repo_bundle",
            "repo_bundle",
            rendered,
            repo=f"{bundle.owner}/{bundle.name}",
            metadata={
                "repo_url": repo_url,
                "file_count": bundle.file_count,
                "total_tokens": bundle.total_tokens,
            },
        )
    except Exception as exc:  # noqa: BLE001 -- best-effort; never break the response
        _log.warning(
            "repo_bundle artifact persist failed for session %s: %s", session_id, exc
        )

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
