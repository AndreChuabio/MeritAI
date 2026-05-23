"""Google Scholar citation data loader.

Two paths:
  * `fetch_via_nimble(scholar_url, api_key)` — live scrape using Nimble's
    `realtime/web` endpoint. Scholar blocks bots; Nimble proxies + renders.
  * `fetch_mock()` — read from `data/scholar_seed.json`. Demo-safe fallback.

The Streamlit Track tab tries Nimble first if `NIMBLE_API_KEY` is set, then
falls back to the mock so the demo never crashes.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests


O1_THRESHOLD = 20  # "20+ citations" is the widely-cited O-1 heuristic.

NIMBLE_REALTIME_URL = "https://api.webit.live/api/v1/realtime/web"


@dataclass
class ScholarData:
    name: str
    scholar_url: str
    total_citations: int
    h_index: int
    by_month: list[dict]
    papers: list[dict]

    def progress_to_o1(self) -> float:
        return min(self.total_citations / O1_THRESHOLD, 1.0)


_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "scholar_seed.json"


def fetch_mock(path: Path = _SEED_PATH) -> ScholarData:
    raw = json.loads(path.read_text())
    return ScholarData(
        name=raw["name"],
        scholar_url=raw["scholar_url"],
        total_citations=raw["total_citations"],
        h_index=raw["h_index"],
        by_month=raw["by_month"],
        papers=raw["papers"],
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

    return ScholarData(
        name="",
        scholar_url=scholar_url,
        total_citations=total,
        h_index=h_index,
        by_month=[],
        papers=papers,
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


def fetch(scholar_url: str | None = None) -> ScholarData:
    """Try Nimble live → fallback to mock. Never raises in the demo path."""
    nimble_key = os.environ.get("NIMBLE_API_KEY")
    if nimble_key and scholar_url:
        try:
            return fetch_via_nimble(scholar_url, nimble_key)
        except Exception:
            pass
    return fetch_mock()
