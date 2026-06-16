"""Venue ranking over the Supabase CFP corpus.

Backend counterpart to cfp_match.rank_venues, but sourced from Supabase
pgvector instead of ClickHouse. Reuses the same semantic-fit + deadline-
proximity scoring so rankings match the legacy app. Nimble live-web
augmentation is intentionally out of scope for this first slice.
"""

from __future__ import annotations

import math

from paperpilot import supabase_client
from paperpilot.cfp_match import VenueMatch, _summary_text
from paperpilot.embed import embed_one
from paperpilot.llm_ingest import ResearchSummary


def rank_venues(
    summary: ResearchSummary,
    limit: int = 5,
    horizon_days: int = 365,
) -> list[VenueMatch]:
    """Embed the summary and rank open CFPs by fit + deadline proximity."""
    q_emb = embed_one(_summary_text(summary))
    rows = supabase_client.match_cfp(q_emb, horizon_days=horizon_days, limit=limit * 2)

    matches: list[VenueMatch] = []
    for cfp_id, name, scope, deadline, url, dist, days in rows:
        sim = 1.0 - float(dist)
        deadline_weight = math.exp(-float(days) / 180.0)  # 6-month half-life
        score = 0.85 * sim + 0.15 * deadline_weight
        matches.append(
            VenueMatch(
                id=cfp_id,
                name=name,
                scope=scope,
                deadline=deadline,
                url=url,
                fit_score=score,
                days_until_deadline=int(days),
            )
        )

    matches.sort(key=lambda m: m.fit_score, reverse=True)
    return matches[:limit]
