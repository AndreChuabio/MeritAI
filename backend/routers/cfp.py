"""CFP router: browse the shared call-for-papers corpus.

Exposes GET /cfp, a plain (non-semantic) chronological listing over the
Supabase cfp table, with optional search/format/upcoming filters. This is
distinct from backend.venues.rank_venues, which ranks CFPs by semantic fit
against a specific paper.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from backend.auth import AuthUser, CurrentUser
from paperpilot import supabase_client

router = APIRouter(prefix="/cfp", tags=["cfp"])


class CfpOut(BaseModel):
    """A single call-for-papers entry."""

    id: str
    name: str
    scope: str
    deadline: date | None
    format: str
    url: str


@router.get("", response_model=list[CfpOut])
def list_cfp(
    q: str | None = None,
    format: str | None = None,
    upcoming: bool = False,
    user: AuthUser = CurrentUser,
) -> list[CfpOut]:
    """List CFPs in chronological order, optionally filtered.

    - q: free-text search over name and scope.
    - format: exact match on the format field.
    - upcoming: when true, restrict to deadlines on or after today.
    """
    rows = supabase_client.list_cfp(
        search=q, format_filter=format, upcoming_only=upcoming
    )
    return [
        CfpOut(id=r[0], name=r[1], scope=r[2], deadline=r[3], format=r[4], url=r[5])
        for r in rows
    ]
