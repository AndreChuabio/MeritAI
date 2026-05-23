"""Match a research summary to upcoming CFPs via ClickHouse vector search.

We embed the summary, run cosineDistance against the cfp table, and rank by
a combination of semantic fit and deadline proximity (closer-deadline venues
get a small boost so we don't recommend something a year out when the work
is ready now).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from paperpilot import trace
from paperpilot.clickhouse_client import get_client
from paperpilot.embed import embed_one
from paperpilot.llm_ingest import ResearchSummary


@dataclass
class VenueMatch:
    id: str
    name: str
    scope: str
    deadline: date
    url: str
    fit_score: float
    days_until_deadline: int


def _summary_text(s: ResearchSummary) -> str:
    return (
        f"Problem: {s.problem}\n"
        f"Contribution: {s.contribution}\n"
        f"Method: {s.method}\n"
        f"Keywords: {', '.join(s.keywords)}"
    )


def rank_venues(
    summary: ResearchSummary,
    session_id: str,
    limit: int = 5,
    horizon_days: int = 365,
) -> list[VenueMatch]:
    """Embed the summary and return the top-N matched CFPs."""
    query_text = _summary_text(summary)

    with trace.step(session_id, "match.embed", chars=len(query_text)) as ctx:
        q_emb = embed_one(query_text)
        ctx["emb_dim"] = len(q_emb)

    client = get_client()

    sql = """
        SELECT
            id, name, scope, deadline, url,
            cosineDistance(scope_emb, {q:Array(Float32)}) AS dist,
            dateDiff('day', today(), deadline) AS days
        FROM cfp
        WHERE deadline > today() AND deadline < addDays(today(), {h:UInt32})
        ORDER BY dist ASC
        LIMIT {n:UInt32}
    """

    with trace.step(session_id, "match.query", horizon=horizon_days, limit=limit) as ctx:
        result = client.query(
            sql, parameters={"q": q_emb, "h": horizon_days, "n": limit}
        )
        ctx["rows"] = len(result.result_rows)

    matches: list[VenueMatch] = []
    for row in result.result_rows:
        cfp_id, name, scope, deadline, url, dist, days = row
        # Cosine distance -> similarity; gently re-rank by deadline proximity.
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
    return matches
