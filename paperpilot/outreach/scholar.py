"""Google Scholar citation data loader.

Two paths:
  * `fetch_via_nimble(scholar_url, api_key)` -- live scrape using Nimble's
    `realtime/web` endpoint. Scholar blocks bots; Nimble proxies + renders.
  * `fetch_mock()` -- read from `data/scholar_seed.json`. Used as an explicit
    fallback when no Scholar URL is configured or the live fetch fails.

Production behavior (post-hackathon): `fetch()` returns a `ScholarData` whose
`source` is either "live" or "mock_fallback". When `source == "mock_fallback"`,
`error` contains a human-readable string the Track UI surfaces in a warning
banner. Silent fallback is no longer the default -- callers can distinguish
demo data from real metrics.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import requests


logger = logging.getLogger(__name__)


O1_THRESHOLD = 20  # "20+ citations" is the widely-cited O-1 heuristic.

NIMBLE_REALTIME_URL = "https://api.webit.live/api/v1/realtime/web"

SourceLiteral = Literal["live", "mock_fallback"]


@dataclass
class ScholarData:
    """Scholar profile metrics.

    Field notes:
      * `total_citations`, `h_index`, `papers`, `by_month` are the original
        hackathon fields; existing call sites read these directly.
      * `by_year` (NEW): cumulative citations per year, sorted ascending.
        Derived from per-paper data on the live path so the Track trajectory
        chart renders without the mock.
      * `source` (NEW): "live" when Nimble fetch succeeded, "mock_fallback"
        when seeded data was substituted.
      * `error` (NEW): populated only when `source == "mock_fallback"`.
    """

    name: str
    scholar_url: str
    total_citations: int
    h_index: int
    by_month: list[dict]
    papers: list[dict]
    by_year: list[tuple[int, int]] = field(default_factory=list)
    source: SourceLiteral = "live"
    error: Optional[str] = None

    @property
    def citations(self) -> int:
        """Alias matching the productionization contract."""
        return self.total_citations

    def progress_to_o1(self) -> float:
        """Fraction of progress toward the O-1 citation heuristic, clamped [0,1]."""
        return min(self.total_citations / O1_THRESHOLD, 1.0)


# Public alias matching the productionization contract.
ScholarResult = ScholarData


_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "scholar_seed.json"


def _cumulative_by_year(papers: list[dict]) -> list[tuple[int, int]]:
    """Sum per-paper citations grouped by publication year, then cumulate.

    Returns [(year, cumulative_citations), ...] sorted ascending. Empty list
    when no papers carry a year+citation pair.
    """
    if not papers:
        return []
    per_year: dict[int, int] = {}
    for p in papers:
        year = p.get("year")
        cites = p.get("citations", 0)
        if not isinstance(year, int) or year <= 0:
            continue
        per_year[year] = per_year.get(year, 0) + int(cites or 0)
    if not per_year:
        return []
    years_sorted = sorted(per_year.keys())
    cumulative: list[tuple[int, int]] = []
    running = 0
    for y in years_sorted:
        running += per_year[y]
        cumulative.append((y, running))
    return cumulative


def fetch_mock(
    path: Path = _SEED_PATH,
    source: SourceLiteral = "live",
    error: Optional[str] = None,
) -> ScholarData:
    """Load the seeded Scholar profile from disk.

    The `source` and `error` arguments let `fetch()` brand the mock as a
    fallback ("mock_fallback" + explanation) versus a deliberate demo load
    ("live"). Defaults preserve historical behavior for direct callers.
    """
    raw = json.loads(path.read_text())
    by_month = raw.get("by_month", [])
    papers = raw.get("papers", [])
    by_year = _cumulative_by_year(papers)
    return ScholarData(
        name=raw["name"],
        scholar_url=raw["scholar_url"],
        total_citations=raw["total_citations"],
        h_index=raw["h_index"],
        by_month=by_month,
        papers=papers,
        by_year=by_year,
        source=source,
        error=error,
    )


# ---- Nimble live path ----


def _parse_scholar_html(html: str, scholar_url: str) -> ScholarData:
    """Best-effort parse of a rendered Scholar profile page."""
    # Citations table: first .gsc_rsb_std cell is total citations (All).
    nums = re.findall(r'class="gsc_rsb_std"[^>]*>(\d+)<', html)
    total = int(nums[0]) if nums else 0
    # h-index is the third numeric cell (All/Recent rows interleaved).
    h_index = int(nums[2]) if len(nums) >= 3 else 0

    papers: list[dict] = []
    for m in re.finditer(
        r'class="gsc_a_at"[^>]*>(?P<title>[^<]+)</a>.*?'
        r'class="gsc_a_ac[^"]*"[^>]*>(?P<cites>\d*)</a>.*?'
        r'class="gsc_a_h[^"]*"[^>]*>(?P<year>\d{4})</span>',
        html,
        re.DOTALL,
    ):
        papers.append({
            "title": m.group("title").strip(),
            "year": int(m.group("year")),
            "citations": int(m.group("cites") or "0"),
        })

    by_year = _cumulative_by_year(papers)

    return ScholarData(
        name="",
        scholar_url=scholar_url,
        total_citations=total,
        h_index=h_index,
        by_month=[],
        papers=papers,
        by_year=by_year,
        source="live",
        error=None,
    )


def fetch_via_nimble(scholar_url: str, api_key: str) -> ScholarData:
    """Live-scrape a Google Scholar profile page via the Nimble API.

    Nimble's `realtime/web` returns the rendered HTML in `html_content`.
    """
    resp = requests.post(
        NIMBLE_REALTIME_URL,
        headers={
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "url": scholar_url,
            "render": True,
            "country": "US",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()
    status_code = body.get("status", {}).get("code", 200)
    if status_code >= 400:
        message = body.get("status", {}).get("message", "unknown")
        raise RuntimeError(f"Nimble scrape failed ({status_code}): {message}")
    html = body.get("html_content") or body.get("body", "")
    return _parse_scholar_html(html, scholar_url)


def fetch(scholar_url: Optional[str] = None) -> ScholarData:
    """Fetch Scholar metrics with explicit fallback semantics.

    Behavior:
      * `scholar_url` is None/empty -> mock with source="mock_fallback" and
        an error explaining no URL is configured.
      * Nimble key missing -> mock with source="mock_fallback" and an error
        explaining the integration isn't configured.
      * Live fetch raises -> mock with source="mock_fallback" and the
        original exception summarized in `error`; original exception logged.
      * Live fetch succeeds -> ScholarData with source="live", error=None.
    """
    if not scholar_url:
        return fetch_mock(
            source="mock_fallback",
            error=(
                "No Scholar URL configured. Set one in your profile to see "
                "real metrics."
            ),
        )

    nimble_key = os.environ.get("NIMBLE_API_KEY")
    if not nimble_key:
        return fetch_mock(
            source="mock_fallback",
            error=(
                "Nimble integration not configured (NIMBLE_API_KEY missing). "
                "Showing seeded sample."
            ),
        )

    try:
        return fetch_via_nimble(scholar_url, nimble_key)
    except Exception as exc:
        logger.exception("Scholar live fetch failed for %s", scholar_url)
        return fetch_mock(
            source="mock_fallback",
            error=f"Live fetch failed: {exc}. Showing seeded sample.",
        )
