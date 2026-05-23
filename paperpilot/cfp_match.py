"""Match a research summary to upcoming CFPs via ClickHouse vector search.

We embed the summary, run cosineDistance against the cfp table, and rank by
a combination of semantic fit and deadline proximity (closer-deadline venues
get a small boost so we don't recommend something a year out when the work
is ready now).

Nimble augmentation: before ranking, we ALSO query Nimble Search for live
web hits on "<keyword> conference 2026 paper submission deadline" using
the summary's keywords. Each web hit is embedded and scored against the
summary the same way ClickHouse candidates are, then merged into the
candidate pool. This is how a NEW venue the curated `cfp_seed.json`
doesn't know about can still appear in the top-5 -- the live web is the
source of truth, the curated corpus is the indexed cache.

Nimble is best-effort: if NIMBLE_API_KEY is unset or the call times out,
the candidate pool just falls back to the ClickHouse-only set.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta

from paperpilot import nimble_client, trace
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


_DEADLINE_RE = re.compile(
    r"(?:deadline|due|submission)[^0-9A-Za-z]{0,20}"
    r"([A-Za-z]+\s+\d{1,2},?\s*20\d{2}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_deadline(text: str, default_days_out: int = 180) -> tuple[date, int]:
    """Best-effort: pull a date from snippet text. Returns (deadline_date, days_until).

    On failure, returns a neutral `default_days_out` placeholder so the venue
    still ranks reasonably and doesn't get a 0-day urgency boost.
    """
    m = _DEADLINE_RE.search(text)
    if m:
        raw = m.group(1).strip().rstrip(",")
        # ISO date
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            try:
                d = date.fromisoformat(raw)
                return d, (d - date.today()).days
            except ValueError:
                pass
        # "September 15, 2026" / "Sep 15 2026"
        parts = re.split(r"[\s,]+", raw)
        if len(parts) >= 3:
            mon_str = parts[0][:3].lower()
            try:
                month = _MONTHS[mon_str]
                day = int(parts[1])
                year = int(parts[2])
                d = date(year, month, day)
                return d, (d - date.today()).days
            except (KeyError, ValueError):
                pass
    fallback = date.today() + timedelta(days=default_days_out)
    return fallback, default_days_out


def _nimble_candidate_venues(
    summary: ResearchSummary,
    q_emb: list[float],
    session_id: str,
    max_hits: int = 3,
) -> list[VenueMatch]:
    """Live-web venue discovery via Nimble Search.

    Returns synthetic `VenueMatch` rows with id=`nimble:<idx>`. Embeds each
    hit's title+snippet and computes the same cosine-similarity score the
    ClickHouse path uses, so Nimble venues compete fairly with curated ones.
    """
    if not nimble_client.is_configured():
        return []

    # Build 1-2 focused queries from the summary's top keywords so we cast
    # a wide-but-relevant net.
    year = date.today().year if date.today().month < 9 else date.today().year + 1
    topic = (
        " ".join(summary.keywords[:3])
        if summary.keywords
        else summary.contribution[:80]
    )
    query = f"{topic} conference {year} paper submission deadline call for papers"

    hits = nimble_client.search(query, session_id, k=max_hits * 2)
    if not hits:
        return []

    candidates: list[VenueMatch] = []
    with trace.step(
        session_id, "match.nimble_augment", query=query[:120], k=max_hits
    ) as ctx:
        for idx, hit in enumerate(hits[: max_hits * 2]):
            scope_text = (hit.title + " — " + hit.snippet).strip(" —")
            if not scope_text or len(scope_text) < 20:
                continue
            try:
                hit_emb = embed_one(scope_text)
            except Exception:  # noqa: BLE001 -- one bad hit shouldn't kill the augment
                continue
            # Cosine similarity against the summary embedding.
            num = sum(a * b for a, b in zip(q_emb, hit_emb))
            denom = math.sqrt(sum(a * a for a in q_emb)) * math.sqrt(
                sum(b * b for b in hit_emb)
            )
            sim = (num / denom) if denom else 0.0
            deadline, days = _parse_deadline(scope_text)
            # Same scoring formula as the ClickHouse path so rankings compose.
            deadline_weight = math.exp(-float(days) / 180.0) if days >= 0 else 0.0
            score = 0.85 * sim + 0.15 * deadline_weight
            candidates.append(
                VenueMatch(
                    id=f"nimble:{idx}",
                    name=hit.title[:120] or hit.url,
                    scope=hit.snippet[:400] or scope_text[:400],
                    deadline=deadline,
                    url=hit.url,
                    fit_score=score,
                    days_until_deadline=int(days),
                )
            )
            if len(candidates) >= max_hits:
                break
        ctx["returned"] = len(candidates)
    return candidates


def rank_venues(
    summary: ResearchSummary,
    session_id: str,
    limit: int = 5,
    horizon_days: int = 365,
) -> list[VenueMatch]:
    """Embed the summary, augment with live Nimble venue discovery, return top-N."""
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
            sql, parameters={"q": q_emb, "h": horizon_days, "n": limit * 2}
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

    # Merge in live-web candidates from Nimble Search (best-effort).
    nimble_matches = _nimble_candidate_venues(summary, q_emb, session_id, max_hits=3)
    matches.extend(nimble_matches)

    matches.sort(key=lambda m: m.fit_score, reverse=True)
    return matches[:limit]
