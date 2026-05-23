"""Nimble Search + Extract API client.

Used by the Market > Blast tab to surface real LinkedIn profiles + (when
extractable) emails for people matching a free-form outreach criteria.

Auth: `Authorization: Bearer <NIMBLE_API_KEY>`
Base: `https://sdk.nimbleway.com/v1`

Endpoints exercised here:
  - POST /v1/search    Real-time web search; we use `focus=social` + a
                       `site:linkedin.com/in` augment to find people.
  - POST /v1/extract   Optional: pull structured data from a target page.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_BASE = "https://sdk.nimbleway.com/v1"


class NimbleAPIError(Exception):
    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        super().__init__(f"Nimble API {status}: {body!r}")


@dataclass
class NimbleClient:
    api_key: str
    base: str = DEFAULT_BASE
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls) -> "NimbleClient":
        return cls(api_key=os.environ["NIMBLE_API_KEY"])

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(kwargs.pop("headers", {}) or {})
        resp = requests.request(
            method, url, headers=headers, timeout=self.timeout_s, **kwargs
        )
        if not (200 <= resp.status_code < 300):
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise NimbleAPIError(resp.status_code, body)
        return resp.json() if resp.content else {}

    def search(
        self,
        query: str,
        focus: str = "general",
        max_results: int = 5,
        search_depth: str = "lite",
    ) -> list[dict]:
        body = {
            "query": query,
            "focus": focus,
            "max_results": max_results,
            "search_depth": search_depth,
        }
        resp = self._request("POST", "/search", json=body)
        return resp.get("results", []) if isinstance(resp, dict) else []

    def find_people(self, criteria: str, limit: int = 5) -> list[dict]:
        """LinkedIn-targeted people search.

        Augments the user's criteria with `site:linkedin.com/in` so the
        results are profile pages, and uses `focus=social` so Nimble's
        agents prioritise social platforms.
        """
        query = f"site:linkedin.com/in {criteria}".strip()
        return self.search(query, focus="social", max_results=limit)

    def extract(self, url: str, render: bool = True) -> dict:
        body = {"url": url, "render": render}
        return self._request("POST", "/extract", json=body)
