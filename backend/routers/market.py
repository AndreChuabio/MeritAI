"""Market router: user profile + outreach drafting endpoints.

All endpoints require authentication and are scoped to the caller's user.id.
Persistence lives in backend.services.market_service over Supabase; LLM and
Senso generation is delegated to the existing paperpilot.outreach pipeline.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth import AuthUser, CurrentUser
from backend.services import market_service

router = APIRouter(prefix="/market", tags=["market"])


class ProfileOut(BaseModel):
    """A user's outreach profile."""

    name: str = ""
    title: str = ""
    about: str = ""
    voice_tone: str = ""
    github_url: str = ""
    linkedin_url: str = ""
    scholar_url: str = ""
    site_url: str = ""
    resume_text: str = ""


class ProfileUpdate(BaseModel):
    """Mutable profile fields. Omitted fields are left unchanged."""

    name: str | None = None
    title: str | None = None
    about: str | None = None
    voice_tone: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    scholar_url: str | None = None
    site_url: str | None = None
    resume_text: str | None = None


class OutreachGenerateRequest(BaseModel):
    """Request body for generating outreach drafts."""

    purpose: str = Field(..., description="VISA, CAREER, NETWORK, BRAND, or SERVICE")
    context: str = Field("", description="Author context to seed the drafts")


class DraftCardOut(BaseModel):
    """One generated draft card for a single channel."""

    channel: str
    content_type_id: str
    sample_job_id: str
    markdown: str
    draft_id: str = ""
    error: str | None = None


class OutreachLogRow(BaseModel):
    """A recorded outreach generation event."""

    id: int
    ts: str | None = None
    purpose: str
    channel: str
    content_type_id: str
    sample_job_id: str
    draft_id: str
    posted: bool


def _profile_out(profile: market_service.Profile) -> ProfileOut:
    """Map a service Profile to the API response model (drops user_id)."""
    return ProfileOut(
        name=profile.name,
        title=profile.title,
        about=profile.about,
        voice_tone=profile.voice_tone,
        github_url=profile.github_url,
        linkedin_url=profile.linkedin_url,
        scholar_url=profile.scholar_url,
        site_url=profile.site_url,
        resume_text=profile.resume_text,
    )


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: AuthUser = CurrentUser) -> ProfileOut:
    """Return the caller's profile, with empty defaults if none exists."""
    return _profile_out(market_service.get_profile(user.id))


@router.put("/profile", response_model=ProfileOut)
def put_profile(
    body: ProfileUpdate, user: AuthUser = CurrentUser
) -> ProfileOut:
    """Upsert the caller's profile and return the stored result."""
    fields = body.model_dump(exclude_none=True)
    profile = market_service.upsert_profile(user.id, fields)
    return _profile_out(profile)


@router.post("/outreach/generate", response_model=list[DraftCardOut])
def generate_outreach(
    body: OutreachGenerateRequest, user: AuthUser = CurrentUser
) -> list[DraftCardOut]:
    """Generate draft cards for a purpose and log each event for the caller."""
    try:
        cards: list[dict[str, Any]] = market_service.generate_outreach(
            user_id=user.id, purpose=body.purpose, context=body.context
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return [DraftCardOut(**card) for card in cards]


@router.get("/outreach/log", response_model=list[OutreachLogRow])
def get_outreach_log(
    limit: int = 50, user: AuthUser = CurrentUser
) -> list[OutreachLogRow]:
    """Return the caller's recent outreach_log rows, newest first."""
    rows = market_service.list_outreach_log(user.id, limit=limit)
    return [OutreachLogRow(**row) for row in rows]
