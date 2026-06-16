"""PaperPilot FastAPI backend.

First Phase 2 slice: health, identity, and venue matching over Supabase.
Ingest / draft / evidence / outreach endpoints follow in subsequent slices.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.auth import AuthUser, CurrentUser
from backend.routers import draft, evidence, export, ingest, market, plugin
from backend.venues import rank_venues
from paperpilot import supabase_client
from paperpilot.llm_ingest import ResearchSummary

load_dotenv()

app = FastAPI(title="PaperPilot API", version="0.1.0")

# CORS for the Next.js frontend. Origins are configurable so preview and
# production deploys can be allowlisted without a code change.
_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Feature routers. Core routes (/health, /me, /match) stay defined inline below.
app.include_router(ingest.router)
app.include_router(draft.router)
app.include_router(export.router)
app.include_router(plugin.router)
app.include_router(evidence.router)
app.include_router(market.router)


class HealthResponse(BaseModel):
    status: str
    database: bool


class VenueResponse(BaseModel):
    id: str
    name: str
    scope: str
    deadline: str
    url: str
    fit_score: float
    days_until_deadline: int


class MatchRequest(BaseModel):
    summary: ResearchSummary
    limit: int = 5
    horizon_days: int = 365


class MeResponse(BaseModel):
    id: str
    email: str | None


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe. Reports whether the Supabase connection is reachable."""
    db_ok = False
    try:
        conn = supabase_client.get_conn()
        try:
            conn.execute("SELECT 1")
            db_ok = True
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 -- health must never raise
        db_ok = False
    return HealthResponse(status="ok", database=db_ok)


@app.get("/me", response_model=MeResponse)
def me(user: AuthUser = CurrentUser) -> MeResponse:
    """Return the authenticated caller (proves the auth wire end-to-end)."""
    return MeResponse(id=user.id, email=user.email)


@app.post("/match", response_model=list[VenueResponse])
def match(req: MatchRequest, user: AuthUser = CurrentUser) -> list[VenueResponse]:
    """Rank open CFP venues for a research summary via Supabase pgvector."""
    matches = rank_venues(req.summary, limit=req.limit, horizon_days=req.horizon_days)
    return [
        VenueResponse(
            id=m.id,
            name=m.name,
            scope=m.scope,
            deadline=m.deadline.isoformat() if m.deadline else "",
            url=m.url,
            fit_score=round(m.fit_score, 4),
            days_until_deadline=m.days_until_deadline,
        )
        for m in matches
    ]
