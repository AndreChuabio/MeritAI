"""Export router: assemble LaTeX + BibTeX and persist the artifact.

Wraps paperpilot.latex_export.export_paper over the FastAPI + Supabase layer.
The request carries the structured research summary, the chosen venue, the
drafted section text (markdown), and an optional list of citations. We adapt
those into the dataclasses export_paper expects (ResearchSummary, VenueMatch,
dict[str, DraftSection]) without re-implementing any LaTeX logic, then persist
the rendered .tex and .bib to session_artifacts.

Persistence is best-effort: a Supabase outage must never block the download
the caller is waiting on, so the inserts are wrapped and swallowed.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.auth import AuthUser, CurrentUser
from paperpilot import supabase_client
from paperpilot.arxiv_lookup import PaperMeta
from paperpilot.cfp_match import VenueMatch
from paperpilot.draft import DraftSection
from paperpilot.latex_export import export_paper
from paperpilot.llm_ingest import ResearchSummary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])


class CitationIn(BaseModel):
    """A single citation to ground in the references.bib output."""

    id: str
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int = 0
    abstract: str = ""


class VenueIn(BaseModel):
    """Minimal venue descriptor needed for the title block and persistence."""

    name: str
    scope: str = ""
    url: str = ""


class ExportRequest(BaseModel):
    """Body for POST /export."""

    summary: ResearchSummary
    venue: VenueIn
    sections: dict[str, str]
    citations: list[CitationIn] = Field(default_factory=list)
    session_id: str = "export"
    repo: str = ""


class ExportResponse(BaseModel):
    """Rendered LaTeX source and its companion BibTeX."""

    tex: str
    bib: str


def _to_venue_match(venue: VenueIn) -> VenueMatch:
    """Adapt the request venue into the VenueMatch export_paper consumes.

    Only name/scope/url are meaningful for export; the scoring and deadline
    fields are filled with neutral placeholders since they do not affect the
    rendered document.
    """
    return VenueMatch(
        id="",
        name=venue.name,
        scope=venue.scope,
        deadline=date.today(),
        url=venue.url,
        fit_score=0.0,
        days_until_deadline=0,
    )


def _to_sections(
    sections: dict[str, str], citations: list[CitationIn]
) -> dict[str, DraftSection]:
    """Wrap raw section markdown into DraftSection records for export_paper.

    Citations are attached to the related-work section so export_paper emits a
    BibTeX entry for each via arxiv_lookup.bibtex_for. The inline [arxiv:id]
    markers in the section text are converted to \\cite{} calls downstream.
    """
    metas = [
        PaperMeta(
            id=c.id,
            title=c.title,
            authors=list(c.authors),
            year=c.year,
            abstract=c.abstract,
        )
        for c in citations
    ]
    drafts: dict[str, DraftSection] = {}
    for name, text in sections.items():
        drafts[name] = DraftSection(name=name, text=text or "")
    # Ensure the citations land on a section export_paper iterates over for
    # BibTeX. Prefer the related-work section; create it if absent.
    if metas:
        target = drafts.get("related") or DraftSection(name="related", text="")
        target.citations = metas
        drafts["related"] = target
    return drafts


def _persist(
    session_id: str,
    user_id: str,
    tex: str,
    bib: str,
    repo: str,
    venue: str,
) -> None:
    """Best-effort persistence of both artifacts to session_artifacts.

    Failures are logged and swallowed so the caller's response is never
    blocked by a transient Supabase issue.
    """
    conn = None
    try:
        conn = supabase_client.get_conn()
        supabase_client.insert_artifact(
            session_id,
            user_id,
            "latex",
            "paper.tex",
            tex,
            repo=repo,
            venue=venue,
            conn=conn,
        )
        supabase_client.insert_artifact(
            session_id,
            user_id,
            "bibtex",
            "references.bib",
            bib,
            repo=repo,
            venue=venue,
            conn=conn,
        )
    except Exception:  # noqa: BLE001 -- persistence must never block the download
        logger.warning("export artifact persistence failed", exc_info=True)
    finally:
        if conn is not None:
            conn.close()


@router.post("/export", response_model=ExportResponse)
def export(req: ExportRequest, user: AuthUser = CurrentUser) -> ExportResponse:
    """Assemble LaTeX + BibTeX from drafted sections and persist the result."""
    venue = _to_venue_match(req.venue)
    sections = _to_sections(req.sections, req.citations)
    tex, bib = export_paper(req.summary, venue, sections)
    _persist(req.session_id, user.id, tex, bib, req.repo, req.venue.name)
    return ExportResponse(tex=tex, bib=bib)
