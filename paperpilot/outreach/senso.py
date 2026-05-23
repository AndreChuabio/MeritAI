"""Senso API client.

Wraps the small surface PaperPilot's Outreach workflow needs:
  - Brand Kit (GET/PUT)
  - Content Types (list/create/get_or_create)
  - Knowledge Base (ingest)
  - Product Lines (list/create)
  - Content Generation (sample + poll)
  - Citation Trends + Drafts (read-only)

Auth: X-API-Key header per https://docs.senso.ai/docs/authentication.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Literal

import requests


DEFAULT_BASE = "https://apiv2.senso.ai/api/v1"


class SensoAPIError(Exception):
    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        super().__init__(f"Senso API {status}: {body!r}")


@dataclass
class Senso:
    api_key: str
    base: str = DEFAULT_BASE
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls) -> "Senso":
        return cls(
            api_key=os.environ["SENSO_API_KEY"],
            base=os.environ.get("SENSO_BASE_URL", DEFAULT_BASE),
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base.rstrip('/')}/{path.lstrip('/')}"
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        headers.update(kwargs.pop("headers", {}) or {})
        resp = requests.request(
            method, url, headers=headers, timeout=self.timeout_s, **kwargs
        )
        if not (200 <= resp.status_code < 300):
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise SensoAPIError(resp.status_code, body)
        if not resp.content:
            return {}
        return resp.json()

    # ---- Brand Kit ----

    def get_brand_kit(self) -> dict:
        return self._request("GET", "/org/brand-kit")

    def put_brand_kit(self, payload: dict) -> dict:
        return self._request("PUT", "/org/brand-kit", json=payload)

    # ---- Content Types ----

    @staticmethod
    def _normalize_ct(d: dict) -> dict:
        """Add an `id` alias from `content_type_id` so callers can use either."""
        if "content_type_id" in d and "id" not in d:
            d = {**d, "id": d["content_type_id"]}
        return d

    def list_content_types(self) -> list[dict]:
        resp = self._request("GET", "/org/content-types")
        if isinstance(resp, list):
            items = resp
        else:
            # Senso wraps under `content_types`; older docs hinted at `items`.
            items = resp.get("content_types") or resp.get("items") or []
        return [self._normalize_ct(it) for it in items]

    def create_content_type(self, name: str, config: dict) -> dict:
        resp = self._request(
            "POST",
            "/org/content-types",
            json={"name": name, "config": config},
        )
        return self._normalize_ct(resp)

    def delete_content_type(self, content_type_id: str) -> None:
        self._request("DELETE", f"/org/content-types/{content_type_id}")

    def get_or_create_content_type(self, name: str, config: dict) -> str:
        for item in self.list_content_types():
            if item.get("name") == name:
                return item["id"]
        created = self.create_content_type(name, config)
        return created["id"]

    # ---- Knowledge Base ----

    def kb_ingest(self, title: str, body: str, source_url: str | None = None) -> dict:
        payload: dict = {"title": title, "body": body}
        if source_url:
            payload["source_url"] = source_url
        return self._request("POST", "/org/knowledge-base/ingest", json=payload)

    # ---- Product Lines ----

    def list_product_lines(self) -> list[dict]:
        resp = self._request("GET", "/org/product-lines")
        if isinstance(resp, list):
            return resp
        return resp.get("items", [])

    def create_product_line(self, name: str, description: str) -> dict:
        return self._request(
            "POST",
            "/org/product-lines",
            json={"name": name, "description": description},
        )

    # ---- Questions (geo_questions / prompts) ----

    # Senso enforces a 255-char cap on question_text. Trim to 240 for margin.
    QUESTION_TEXT_MAX = 240

    def create_question(self, question_text: str, q_type: str = "awareness") -> str:
        """Create a geo_question; return its id.

        Senso requires `question_text` <= 255 chars. We trim to 240 and
        append an ellipsis so the model sees it was clipped. Full author
        context already lives in the brand-kit + content-type template.
        """
        text = (question_text or "").strip()
        if len(text) > self.QUESTION_TEXT_MAX:
            text = text[: self.QUESTION_TEXT_MAX - 1].rstrip() + "…"
        resp = self._request(
            "POST",
            "/org/questions",
            json={"question_text": text, "type": q_type},
        )
        return resp["geo_question_id"]

    # ---- Content Generation ----

    def generate_sample(self, content_type_id: str, context: str) -> str:
        """Kick off async sample generation; return the job id.

        Senso requires a `geo_question_id` (the topic prompt). We create
        one on the fly from the caller's `context` so the orchestrator
        stays a single call.
        """
        geo_question_id = self.create_question(context)
        resp = self._request(
            "POST",
            "/org/content-generation/sample",
            json={
                "content_type_id": content_type_id,
                "geo_question_id": geo_question_id,
            },
        )
        return resp["sample_job_id"]

    def get_sample_job(self, job_id: str) -> dict:
        return self._request("GET", f"/org/content-generation/sample-jobs/{job_id}")

    def poll_until_done(
        self,
        job_id: str,
        timeout_s: float = 30.0,
        interval_s: float = 1.0,
    ) -> dict:
        deadline = time.monotonic() + timeout_s
        while True:
            job = self.get_sample_job(job_id)
            if job.get("status") == "completed":
                return job
            if job.get("status") == "failed":
                raise SensoAPIError(500, job)
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Senso sample job {job_id} did not complete in {timeout_s}s"
                )
            time.sleep(interval_s)

    # ---- Citation Trends + Drafts (read-only) ----

    def citation_trends(self, scope: Literal["owned", "external"]) -> dict:
        return self._request("GET", f"/org/citation-trends/{scope}")

    def list_drafts(self, limit: int = 10) -> list[dict]:
        resp = self._request("GET", "/org/drafts", params={"limit": limit})
        if isinstance(resp, list):
            return resp
        return resp.get("items", [])
