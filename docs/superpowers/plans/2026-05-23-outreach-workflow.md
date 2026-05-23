# Outreach Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three Streamlit tabs (Brand / Outreach / Track) to PaperPilot that front-end a Senso workspace, generate purpose-driven outreach drafts via Senso APIs, and surface a visa-progress dashboard combining Google Scholar (academic) and Senso (AI) citation signals.

**Architecture:** New `paperpilot/outreach/` package holds a Senso client, purpose→channel mapping, orchestrator, Scholar mock loader, and ClickHouse audit helpers. A seed script idempotently creates Senso content types + product lines. `app.py` gets three new tabs. Every Senso call is wrapped in the existing `trace.step` context manager so Lapdog/Datadog observability is preserved.

**Tech Stack:** Python 3.11, Streamlit, ClickHouse Cloud (`clickhouse-connect`), `requests` (Senso HTTP), `pytest` (test framework — added by this plan), `responses` library for HTTP mocking in tests.

**Reference spec:** `docs/superpowers/specs/2026-05-23-outreach-workflow-design.md` — read first if you have not.

**Hackathon constraint:** Code freeze 17:00 ET 2026-05-23, demo 17:30. Commit after every passing task. Cut-list in the spec §14 — apply if the clock is winning.

---

## File Map

**Create:**
- `paperpilot/outreach/__init__.py`
- `paperpilot/outreach/purpose.py`
- `paperpilot/outreach/content_types.py`
- `paperpilot/outreach/senso.py`
- `paperpilot/outreach/orchestrator.py`
- `paperpilot/outreach/scholar.py`
- `paperpilot/outreach/log.py`
- `scripts/seed_senso.py`
- `data/scholar_seed.json`
- `tests/__init__.py`
- `tests/outreach/__init__.py`
- `tests/outreach/test_purpose.py`
- `tests/outreach/test_senso.py`
- `tests/outreach/test_orchestrator.py`
- `tests/outreach/test_scholar.py`
- `tests/outreach/test_log.py`
- `tests/outreach/test_seed_senso.py`

**Modify:**
- `pyproject.toml` — add `pytest`, `responses` to dev deps; add `[tool.pytest.ini_options]`
- `.env.example` — add `SENSO_API_KEY` block
- `paperpilot/clickhouse_client.py` — append `user_profile` and `outreach_log` to `SCHEMA_SQL`
- `app.py` — add three tabs (Brand, Outreach, Track)
- `Makefile` — add `make test`, `make seed-senso`, `make outreach-demo` targets

---

## Task 1: Add test infra + outreach package skeleton

**Files:**
- Create: `paperpilot/outreach/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `tests/outreach/__init__.py` (empty)
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1.1: Add pytest + responses to pyproject**

Open `pyproject.toml`. Replace the `dependencies` block by appending two new items, and add a `[dependency-groups]` table at the end:

```toml
[project]
name = "agentichack"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.104.1",
    "arxiv>=4.0.0",
    "clickhouse-connect>=1.0.1",
    "ddtrace>=4.8.7",
    "google-genai>=2.6.0",
    "openai>=2.38.0",
    "pydantic>=2.13.4",
    "pygithub>=2.9.1",
    "python-dotenv>=1.2.2",
    "streamlit>=1.57.0",
    "tiktoken>=0.13.0",
    "requests>=2.32.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "responses>=0.25.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 1.2: Install test deps**

Run: `uv sync --dev`
Expected: installs pytest + responses without errors.

- [ ] **Step 1.3: Create empty package + test scaffolding**

Create `paperpilot/outreach/__init__.py`:
```python
"""Outreach workflow: Senso-backed brand + content drafts + visa-progress dashboard."""
```

Create `tests/__init__.py` (empty file).
Create `tests/outreach/__init__.py` (empty file).

- [ ] **Step 1.4: Verify pytest runs**

Run: `uv run pytest -q`
Expected: `no tests ran` (exit 5 is OK — pytest exits 5 when there are no tests). If you get exit 0 with `no tests ran`, fine too.

- [ ] **Step 1.5: Add SENSO_API_KEY to .env.example**

Append to `/Users/nikkihu/Documents/Github/agentichack/.env.example`:
```
# Senso (brand-kit / content-types / knowledge-base / content-generation)
# Get from: https://app.senso.ai -> API keys (workspace: Agentic-hack)
SENSO_API_KEY=
SENSO_BASE_URL=https://apiv2.senso.ai/api/v1
```

- [ ] **Step 1.6: Commit**

```bash
git add pyproject.toml uv.lock paperpilot/outreach/__init__.py tests/__init__.py tests/outreach/__init__.py .env.example
git commit -m "outreach: scaffold package, tests, deps, SENSO env vars"
```

---

## Task 2: Purpose → channel mapping

**Files:**
- Create: `paperpilot/outreach/purpose.py`
- Create: `tests/outreach/test_purpose.py`

- [ ] **Step 2.1: Write failing test**

Create `tests/outreach/test_purpose.py`:
```python
import pytest
from paperpilot.outreach.purpose import Purpose, PURPOSE_CHANNELS, channels_for


def test_purpose_enum_has_four_values():
    assert {p.value for p in Purpose} == {"VISA", "CAREER", "BRAND", "SERVICE"}


def test_visa_targets_speaker_and_collaboration_emails():
    assert channels_for(Purpose.VISA) == ["email_speaker_pitch", "email_collaboration"]


def test_career_targets_linkedin_dm():
    assert channels_for(Purpose.CAREER) == ["linkedin_dm_career"]


def test_brand_targets_linkedin_post_and_x_thread():
    assert channels_for(Purpose.BRAND) == ["linkedin_post_brand", "x_thread_brand"]


def test_service_targets_three_channels():
    assert channels_for(Purpose.SERVICE) == [
        "linkedin_post_brand",
        "email_service",
        "x_thread_brand",
    ]


def test_channels_for_accepts_string_purpose():
    assert channels_for("VISA") == channels_for(Purpose.VISA)


def test_channels_for_rejects_unknown_purpose():
    with pytest.raises(ValueError):
        channels_for("MYSTERY")
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `uv run pytest tests/outreach/test_purpose.py -v`
Expected: `ModuleNotFoundError: No module named 'paperpilot.outreach.purpose'`.

- [ ] **Step 2.3: Implement purpose module**

Create `paperpilot/outreach/purpose.py`:
```python
"""Purpose enum + purpose -> channel mapping for outreach drafts."""

from __future__ import annotations

from enum import Enum


class Purpose(str, Enum):
    VISA = "VISA"
    CAREER = "CAREER"
    BRAND = "BRAND"
    SERVICE = "SERVICE"


PURPOSE_CHANNELS: dict[Purpose, list[str]] = {
    Purpose.VISA:    ["email_speaker_pitch", "email_collaboration"],
    Purpose.CAREER:  ["linkedin_dm_career"],
    Purpose.BRAND:   ["linkedin_post_brand", "x_thread_brand"],
    Purpose.SERVICE: ["linkedin_post_brand", "email_service", "x_thread_brand"],
}


def channels_for(purpose: Purpose | str) -> list[str]:
    """Return the ordered list of channel content-type names for a purpose."""
    if isinstance(purpose, str):
        try:
            purpose = Purpose(purpose)
        except ValueError as exc:
            raise ValueError(f"Unknown purpose: {purpose!r}") from exc
    return list(PURPOSE_CHANNELS[purpose])
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `uv run pytest tests/outreach/test_purpose.py -v`
Expected: 7 passed.

- [ ] **Step 2.5: Commit**

```bash
git add paperpilot/outreach/purpose.py tests/outreach/test_purpose.py
git commit -m "outreach: Purpose enum + channel mapping (TDD)"
```

---

## Task 3: Senso client — auth, base URL, error type

**Files:**
- Create: `paperpilot/outreach/senso.py`
- Create: `tests/outreach/test_senso.py`

- [ ] **Step 3.1: Write failing test for auth header + base URL**

Create `tests/outreach/test_senso.py`:
```python
import pytest
import responses

from paperpilot.outreach.senso import Senso, SensoAPIError


@responses.activate
def test_senso_sends_api_key_header():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/brand-kit",
        json={"brand_name": "Nikki"},
        status=200,
    )
    s = Senso(api_key="test-key")
    s.get_brand_kit()
    assert responses.calls[0].request.headers["X-API-Key"] == "test-key"


@responses.activate
def test_senso_raises_on_non_2xx():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/brand-kit",
        json={"error": "nope"},
        status=403,
    )
    s = Senso(api_key="test-key")
    with pytest.raises(SensoAPIError) as exc_info:
        s.get_brand_kit()
    assert exc_info.value.status == 403


@responses.activate
def test_senso_respects_custom_base_url():
    responses.add(
        responses.GET,
        "https://staging.senso.ai/v1/org/brand-kit",
        json={"brand_name": "Nikki"},
        status=200,
    )
    s = Senso(api_key="k", base="https://staging.senso.ai/v1")
    s.get_brand_kit()
    assert responses.calls[0].request.url.startswith("https://staging.senso.ai/v1/")
```

- [ ] **Step 3.2: Run test to verify failure**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3.3: Implement minimal Senso client + get_brand_kit**

Create `paperpilot/outreach/senso.py`:
```python
"""Senso API client.

Wraps the small surface PaperPilot's Outreach workflow needs:
  - Brand Kit (GET/PUT)
  - Content Types (list/create/get_or_create)
  - Knowledge Base (ingest)
  - Product Lines (list/create)
  - Content Generation (sample + poll)
  - Citation Trends + Drafts (read-only)
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
    timeout_s: float = 15.0

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
```

- [ ] **Step 3.4: Run tests**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 3 passed.

- [ ] **Step 3.5: Commit**

```bash
git add paperpilot/outreach/senso.py tests/outreach/test_senso.py
git commit -m "outreach: Senso client base — auth header, base URL, error type"
```

---

## Task 4: Senso brand kit — PUT

**Files:**
- Modify: `paperpilot/outreach/senso.py`
- Modify: `tests/outreach/test_senso.py`

- [ ] **Step 4.1: Add failing test**

Append to `tests/outreach/test_senso.py`:
```python
@responses.activate
def test_put_brand_kit_sends_payload():
    captured = {}
    def cb(request):
        captured["body"] = request.body
        return (200, {}, '{"ok": true}')

    responses.add_callback(
        responses.PUT,
        "https://apiv2.senso.ai/api/v1/org/brand-kit",
        callback=cb,
        content_type="application/json",
    )

    s = Senso(api_key="k")
    s.put_brand_kit({
        "brand_name": "Nikki Hu",
        "brand_description": "Clinical ML engineer",
        "voice_and_tone": "warm, evidence-based",
        "guidelines": {"links": {"scholar": "https://scholar.google.com/..."}},
    })
    assert b'"brand_name": "Nikki Hu"' in captured["body"]
    assert b'"voice_and_tone"' in captured["body"]
```

- [ ] **Step 4.2: Run — expect failure**

Run: `uv run pytest tests/outreach/test_senso.py::test_put_brand_kit_sends_payload -v`
Expected: `AttributeError: 'Senso' object has no attribute 'put_brand_kit'`.

- [ ] **Step 4.3: Implement put_brand_kit**

Append inside the `Senso` class in `paperpilot/outreach/senso.py`:
```python
    def put_brand_kit(self, payload: dict) -> dict:
        return self._request("PUT", "/org/brand-kit", json=payload)
```

- [ ] **Step 4.4: Run — expect pass**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 4 passed.

- [ ] **Step 4.5: Commit**

```bash
git add paperpilot/outreach/senso.py tests/outreach/test_senso.py
git commit -m "outreach: Senso put_brand_kit"
```

---

## Task 5: Senso content types — list + create + get_or_create

**Files:**
- Modify: `paperpilot/outreach/senso.py`
- Modify: `tests/outreach/test_senso.py`

- [ ] **Step 5.1: Add failing tests**

Append to `tests/outreach/test_senso.py`:
```python
@responses.activate
def test_list_content_types_returns_items():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"items": [{"id": "a", "name": "linkedin_post_brand"}]},
        status=200,
    )
    s = Senso(api_key="k")
    items = s.list_content_types()
    assert items == [{"id": "a", "name": "linkedin_post_brand"}]


@responses.activate
def test_create_content_type_posts_name_and_config():
    captured = {}
    def cb(request):
        captured["body"] = request.body
        return (201, {}, '{"id": "ct-new"}')
    responses.add_callback(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        callback=cb,
        content_type="application/json",
    )
    s = Senso(api_key="k")
    result = s.create_content_type("x_thread_brand", {"template": "4-6 tweets"})
    assert result == {"id": "ct-new"}
    assert b'"name": "x_thread_brand"' in captured["body"]
    assert b'"template": "4-6 tweets"' in captured["body"]


@responses.activate
def test_get_or_create_returns_existing_id_without_post():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"items": [{"id": "ct-existing", "name": "linkedin_dm_career"}]},
        status=200,
    )
    s = Senso(api_key="k")
    ctid = s.get_or_create_content_type("linkedin_dm_career", {"template": "ignored"})
    assert ctid == "ct-existing"
    # Only one HTTP call total (the GET).
    assert len(responses.calls) == 1


@responses.activate
def test_get_or_create_creates_when_missing():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"items": []},
        status=200,
    )
    responses.add(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"id": "ct-fresh"},
        status=201,
    )
    s = Senso(api_key="k")
    ctid = s.get_or_create_content_type("new_thing", {"template": "..."})
    assert ctid == "ct-fresh"
    assert len(responses.calls) == 2
```

- [ ] **Step 5.2: Run — expect failure**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 4 new failures (AttributeError).

- [ ] **Step 5.3: Implement content type methods**

Append inside the `Senso` class:
```python
    # ---- Content Types ----

    def list_content_types(self) -> list[dict]:
        resp = self._request("GET", "/org/content-types")
        if isinstance(resp, list):
            return resp
        return resp.get("items", [])

    def create_content_type(self, name: str, config: dict) -> dict:
        return self._request(
            "POST",
            "/org/content-types",
            json={"name": name, "config": config},
        )

    def get_or_create_content_type(self, name: str, config: dict) -> str:
        for item in self.list_content_types():
            if item.get("name") == name:
                return item["id"]
        created = self.create_content_type(name, config)
        return created["id"]
```

- [ ] **Step 5.4: Run — expect pass**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 8 passed.

- [ ] **Step 5.5: Commit**

```bash
git add paperpilot/outreach/senso.py tests/outreach/test_senso.py
git commit -m "outreach: Senso content types (list/create/get_or_create, idempotent)"
```

---

## Task 6: Senso content generation — sample + poll

**Files:**
- Modify: `paperpilot/outreach/senso.py`
- Modify: `tests/outreach/test_senso.py`

- [ ] **Step 6.1: Add failing tests**

Append to `tests/outreach/test_senso.py`:
```python
@responses.activate
def test_generate_sample_returns_job_id():
    responses.add(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample",
        json={"sample_job_id": "job-abc", "status": "queued"},
        status=200,
    )
    s = Senso(api_key="k")
    job_id = s.generate_sample(content_type_id="ct-1", context="hello")
    assert job_id == "job-abc"
    body = responses.calls[0].request.body
    assert b'"content_type_id": "ct-1"' in body
    assert b'"context": "hello"' in body


@responses.activate
def test_poll_until_done_returns_completed_result():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample-jobs/job-abc",
        json={"status": "running"},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample-jobs/job-abc",
        json={"status": "completed", "result": {"raw_markdown": "hi"}},
        status=200,
    )
    s = Senso(api_key="k")
    out = s.poll_until_done("job-abc", interval_s=0.01, timeout_s=2.0)
    assert out["result"]["raw_markdown"] == "hi"


@responses.activate
def test_poll_until_done_raises_on_timeout():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample-jobs/stuck",
        json={"status": "running"},
        status=200,
    )
    s = Senso(api_key="k")
    with pytest.raises(TimeoutError):
        s.poll_until_done("stuck", interval_s=0.01, timeout_s=0.05)
```

- [ ] **Step 6.2: Run — expect failure**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 3 new failures.

- [ ] **Step 6.3: Implement generation methods**

Append inside the `Senso` class:
```python
    # ---- Content Generation ----

    def generate_sample(self, content_type_id: str, context: str) -> str:
        """Kick off async sample generation; return the job id.

        NOTE: Senso docs reference a `geo_question_id` form. If the server
        rejects `context`, switch this to create a geo_question first and
        pass that id. The orchestrator does not care which path is used.
        """
        body = {"content_type_id": content_type_id, "context": context}
        resp = self._request("POST", "/org/content-generation/sample", json=body)
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
                raise TimeoutError(f"Senso sample job {job_id} did not complete in {timeout_s}s")
            time.sleep(interval_s)
```

- [ ] **Step 6.4: Run — expect pass**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 11 passed.

- [ ] **Step 6.5: Commit**

```bash
git add paperpilot/outreach/senso.py tests/outreach/test_senso.py
git commit -m "outreach: Senso content-generation sample + polling"
```

---

## Task 7: Senso KB ingest, product lines, citation trends, drafts (read-only stubs)

**Files:**
- Modify: `paperpilot/outreach/senso.py`
- Modify: `tests/outreach/test_senso.py`

- [ ] **Step 7.1: Add failing tests**

Append to `tests/outreach/test_senso.py`:
```python
@responses.activate
def test_kb_ingest_posts_title_and_body():
    responses.add(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/knowledge-base/ingest",
        json={"id": "kb-1"},
        status=200,
    )
    s = Senso(api_key="k")
    out = s.kb_ingest(title="Paper Summary", body="...", source_url="https://x")
    assert out["id"] == "kb-1"


@responses.activate
def test_list_product_lines():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/product-lines",
        json={"items": [{"id": "pl-1", "name": "PaperPilot"}]},
        status=200,
    )
    s = Senso(api_key="k")
    assert s.list_product_lines() == [{"id": "pl-1", "name": "PaperPilot"}]


@responses.activate
def test_citation_trends_owned():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/citation-trends/owned",
        json={"total": 12, "by_day": [{"d": "2026-05-22", "n": 3}]},
        status=200,
    )
    s = Senso(api_key="k")
    out = s.citation_trends("owned")
    assert out["total"] == 12


@responses.activate
def test_list_drafts_returns_items():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/drafts?limit=5",
        json={"items": [{"id": "d1"}]},
        status=200,
        match_querystring=True,
    )
    s = Senso(api_key="k")
    items = s.list_drafts(limit=5)
    assert items == [{"id": "d1"}]
```

- [ ] **Step 7.2: Run — expect failure**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 4 new failures.

- [ ] **Step 7.3: Implement read-only methods + KB ingest + product line create**

Append inside the `Senso` class:
```python
    # ---- Knowledge Base ----

    def kb_ingest(self, title: str, body: str, source_url: str | None = None) -> dict:
        payload = {"title": title, "body": body}
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

    # ---- Citation Trends + Drafts (read-only) ----

    def citation_trends(self, scope: Literal["owned", "external"]) -> dict:
        return self._request("GET", f"/org/citation-trends/{scope}")

    def list_drafts(self, limit: int = 10) -> list[dict]:
        resp = self._request("GET", "/org/drafts", params={"limit": limit})
        if isinstance(resp, list):
            return resp
        return resp.get("items", [])
```

- [ ] **Step 7.4: Run — expect pass**

Run: `uv run pytest tests/outreach/test_senso.py -v`
Expected: 15 passed.

- [ ] **Step 7.5: Commit**

```bash
git add paperpilot/outreach/senso.py tests/outreach/test_senso.py
git commit -m "outreach: Senso KB ingest, product lines, citation trends, drafts"
```

---

## Task 8: ClickHouse schemas + audit helpers

**Files:**
- Modify: `paperpilot/clickhouse_client.py:62-94` (the SCHEMA_SQL list)
- Create: `paperpilot/outreach/log.py`
- Create: `tests/outreach/test_log.py`

- [ ] **Step 8.1: Extend SCHEMA_SQL with user_profile + outreach_log**

Open `paperpilot/clickhouse_client.py`. In the `SCHEMA_SQL` list (lines ~62-94), append two new schema strings before the closing `]`:

```python
    """
    CREATE TABLE IF NOT EXISTS user_profile (
        user_id String,
        name String,
        title String,
        about String,
        voice_tone String,
        github_url String,
        linkedin_url String,
        scholar_url String,
        site_url String,
        resume_text String,
        updated_at DateTime64(3)
    ) ENGINE = ReplacingMergeTree(updated_at) ORDER BY user_id
    """,
    """
    CREATE TABLE IF NOT EXISTS outreach_log (
        ts DateTime64(3) DEFAULT now64(3),
        user_id String,
        purpose String,
        channel String,
        content_type_id String,
        sample_job_id String,
        draft_id String,
        posted UInt8
    ) ENGINE = MergeTree ORDER BY (ts, user_id)
    """,
```

- [ ] **Step 8.2: Write failing tests for log helpers**

Create `tests/outreach/test_log.py`:
```python
from unittest.mock import MagicMock

from paperpilot.outreach.log import (
    log_generate,
    mark_posted,
    upsert_user_profile,
    count_posted,
    UserProfile,
)


def test_upsert_user_profile_inserts_with_now():
    client = MagicMock()
    profile = UserProfile(
        user_id="demo",
        name="Nikki",
        title="ML Eng",
        about="Clinical ML",
        voice_tone="warm",
        github_url="https://github.com/x",
        linkedin_url="https://linkedin.com/in/x",
        scholar_url="https://scholar.google.com/x",
        site_url="https://x.dev",
        resume_text="...",
    )
    upsert_user_profile(profile, client=client)
    client.insert.assert_called_once()
    args, kwargs = client.insert.call_args
    assert args[0] == "user_profile"
    row = args[1][0]
    assert row[0] == "demo"
    assert row[1] == "Nikki"


def test_log_generate_writes_row_and_returns_id():
    client = MagicMock()
    row_id = log_generate(
        user_id="demo",
        purpose="VISA",
        channel="email_speaker_pitch",
        content_type_id="ct-1",
        sample_job_id="job-1",
        client=client,
    )
    assert isinstance(row_id, str) and row_id
    client.insert.assert_called_once()


def test_mark_posted_updates_row():
    client = MagicMock()
    mark_posted(sample_job_id="job-1", draft_id="d-1", client=client)
    client.command.assert_called_once()
    cmd = client.command.call_args[0][0]
    assert "ALTER TABLE outreach_log" in cmd
    assert "posted = 1" in cmd


def test_count_posted_returns_int():
    client = MagicMock()
    client.query.return_value.result_rows = [[7]]
    assert count_posted("demo", client=client) == 7
```

- [ ] **Step 8.3: Run — expect failure**

Run: `uv run pytest tests/outreach/test_log.py -v`
Expected: `ModuleNotFoundError: No module named 'paperpilot.outreach.log'`.

- [ ] **Step 8.4: Implement log module**

Create `paperpilot/outreach/log.py`:
```python
"""ClickHouse audit helpers for the Outreach workflow.

All helpers accept an optional `client` kwarg so unit tests can pass a mock.
In normal use the caller can omit it and a real ClickHouse client is opened.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from paperpilot.clickhouse_client import get_client


@dataclass
class UserProfile:
    user_id: str
    name: str
    title: str
    about: str
    voice_tone: str
    github_url: str
    linkedin_url: str
    scholar_url: str
    site_url: str
    resume_text: str


_USER_PROFILE_COLS = [
    "user_id", "name", "title", "about", "voice_tone",
    "github_url", "linkedin_url", "scholar_url", "site_url",
    "resume_text", "updated_at",
]

_OUTREACH_LOG_COLS = [
    "ts", "user_id", "purpose", "channel",
    "content_type_id", "sample_job_id", "draft_id", "posted",
]


def upsert_user_profile(profile: UserProfile, client: Any | None = None) -> None:
    client = client or get_client()
    row = [
        profile.user_id, profile.name, profile.title, profile.about,
        profile.voice_tone, profile.github_url, profile.linkedin_url,
        profile.scholar_url, profile.site_url, profile.resume_text,
        datetime.now(),
    ]
    client.insert("user_profile", [row], column_names=_USER_PROFILE_COLS)


def log_generate(
    user_id: str,
    purpose: str,
    channel: str,
    content_type_id: str,
    sample_job_id: str,
    client: Any | None = None,
) -> str:
    """Insert a generate-event row. Returns the sample_job_id (acts as the row id)."""
    client = client or get_client()
    row = [
        datetime.now(),
        user_id, purpose, channel, content_type_id,
        sample_job_id, "", 0,
    ]
    client.insert("outreach_log", [row], column_names=_OUTREACH_LOG_COLS)
    return sample_job_id


def mark_posted(sample_job_id: str, draft_id: str, client: Any | None = None) -> None:
    client = client or get_client()
    # ClickHouse ALTER UPDATE is async but adequate for our audit purpose.
    client.command(
        "ALTER TABLE outreach_log UPDATE posted = 1, draft_id = "
        f"'{draft_id}' WHERE sample_job_id = '{sample_job_id}'"
    )


def count_posted(user_id: str, client: Any | None = None) -> int:
    client = client or get_client()
    result = client.query(
        "SELECT count() FROM outreach_log WHERE user_id = {u:String} AND posted = 1",
        parameters={"u": user_id},
    )
    return int(result.result_rows[0][0])
```

- [ ] **Step 8.5: Run — expect pass**

Run: `uv run pytest tests/outreach/test_log.py -v`
Expected: 4 passed.

- [ ] **Step 8.6: Commit**

```bash
git add paperpilot/clickhouse_client.py paperpilot/outreach/log.py tests/outreach/test_log.py
git commit -m "outreach: ClickHouse user_profile + outreach_log schemas + helpers"
```

---

## Task 9: Scholar mock loader

**Files:**
- Create: `data/scholar_seed.json`
- Create: `paperpilot/outreach/scholar.py`
- Create: `tests/outreach/test_scholar.py`

- [ ] **Step 9.1: Create the mock data file**

Create `data/scholar_seed.json`:
```json
{
  "name": "Nikki Hu",
  "scholar_url": "https://scholar.google.com/citations?user=DEMO",
  "total_citations": 14,
  "h_index": 5,
  "by_month": [
    {"date": "2025-08", "count": 1},
    {"date": "2025-09", "count": 2},
    {"date": "2025-10", "count": 3},
    {"date": "2025-11", "count": 5},
    {"date": "2025-12", "count": 7},
    {"date": "2026-01", "count": 9},
    {"date": "2026-02", "count": 11},
    {"date": "2026-03", "count": 12},
    {"date": "2026-04", "count": 13},
    {"date": "2026-05", "count": 14}
  ],
  "papers": [
    {"title": "Federated LLMs for Clinical Notes", "year": 2025, "citations": 7},
    {"title": "Differential Privacy in EHR Pipelines", "year": 2025, "citations": 4},
    {"title": "Retrieval Calibration for Medical QA", "year": 2026, "citations": 3}
  ]
}
```

- [ ] **Step 9.2: Write failing test**

Create `tests/outreach/test_scholar.py`:
```python
from paperpilot.outreach.scholar import fetch_mock, ScholarData, O1_THRESHOLD


def test_fetch_mock_loads_seed_file():
    data = fetch_mock()
    assert isinstance(data, ScholarData)
    assert data.total_citations == 14
    assert len(data.by_month) == 10


def test_o1_threshold_constant_is_20():
    assert O1_THRESHOLD == 20


def test_progress_to_o1_fraction():
    data = fetch_mock()
    assert 0.0 <= data.progress_to_o1() <= 1.0
    # 14 / 20 = 0.7
    assert abs(data.progress_to_o1() - 0.7) < 1e-6
```

- [ ] **Step 9.3: Run — expect failure**

Run: `uv run pytest tests/outreach/test_scholar.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 9.4: Implement scholar module**

Create `paperpilot/outreach/scholar.py`:
```python
"""Google Scholar citation data loader.

Demo path: read from `data/scholar_seed.json` (committed).
Stretch path (not in this commit): live fetch via Nimble proxy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

O1_THRESHOLD = 20  # "20+ citations" is the widely-cited O-1 heuristic.


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
```

- [ ] **Step 9.5: Run — expect pass**

Run: `uv run pytest tests/outreach/test_scholar.py -v`
Expected: 3 passed.

- [ ] **Step 9.6: Commit**

```bash
git add data/scholar_seed.json paperpilot/outreach/scholar.py tests/outreach/test_scholar.py
git commit -m "outreach: Google Scholar mock loader + O-1 progress fraction"
```

---

## Task 10: Content-type configs + idempotent Senso seed script

**Files:**
- Create: `paperpilot/outreach/content_types.py`
- Create: `scripts/seed_senso.py`
- Create: `tests/outreach/test_seed_senso.py`

- [ ] **Step 10.0: Create content_types module**

Create `paperpilot/outreach/content_types.py`:
```python
"""Templates used by Senso to shape generated content.

These map 1:1 to the channels referenced in `purpose.PURPOSE_CHANNELS`.
The seed script creates one Senso content type per entry here; the
orchestrator passes the matching config into `get_or_create_content_type`
in case the type does not yet exist on first run.
"""

from __future__ import annotations


CONTENT_TYPE_CONFIGS: dict[str, dict] = {
    "linkedin_post_brand": {
        "template": (
            "A first-person LinkedIn post, 200-300 words. Open with a hook, "
            "deliver one concrete insight, end with a single question to the "
            "reader. No emojis. No hashtags."
        ),
        "writing_rules": "Under 1300 chars. Plain text. No links inline.",
    },
    "linkedin_dm_career": {
        "template": (
            "A short LinkedIn direct message, under 600 chars. Warm intro "
            "tone, reference one shared interest, end with one explicit ask."
        ),
        "writing_rules": "Address by first name if known. No corporate jargon.",
    },
    "x_thread_brand": {
        "template": (
            "A 4-6 tweet thread. First tweet hooks; each subsequent tweet "
            "delivers one point; last tweet has a CTA. Number each tweet `1/`."
        ),
        "writing_rules": "Each tweet ≤ 280 characters.",
    },
    "email_speaker_pitch": {
        "template": (
            "A formal pitch email to a conference organizer. Subject line on "
            "the first line. Body 150-250 words. Names a specific session "
            "slot and concrete topic the author can speak on."
        ),
        "writing_rules": "Sign with the author's name. No emojis.",
    },
    "email_collaboration": {
        "template": (
            "A warm academic outreach email asking about collaboration. "
            "Reference a shared topic explicitly. 150-250 words. Soft ask."
        ),
        "writing_rules": "Reply-friendly closing.",
    },
    "email_service": {
        "template": (
            "A value-first service outreach email. Open with what the "
            "recipient gets. 150-200 words. One CTA only, in the last line."
        ),
        "writing_rules": "No hard sell language.",
    },
}
```

- [ ] **Step 10.1: Write failing test**

Create `tests/outreach/test_seed_senso.py`:
```python
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.seed_senso import seed_content_types
from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS


def test_seed_creates_all_content_types_when_workspace_empty():
    senso = MagicMock()
    senso.list_content_types.return_value = []
    senso.create_content_type.side_effect = (
        lambda name, config: {"id": f"ct-{name}"}
    )

    ids = seed_content_types(senso)

    assert set(ids.keys()) == set(CONTENT_TYPE_CONFIGS.keys())
    assert senso.create_content_type.call_count == len(CONTENT_TYPE_CONFIGS)


def test_seed_is_idempotent_when_all_exist():
    existing = [
        {"id": f"ct-{name}", "name": name} for name in CONTENT_TYPE_CONFIGS
    ]
    senso = MagicMock()
    senso.list_content_types.return_value = existing

    ids = seed_content_types(senso)

    assert ids == {name: f"ct-{name}" for name in CONTENT_TYPE_CONFIGS}
    senso.create_content_type.assert_not_called()


def test_content_type_configs_cover_all_channels():
    from paperpilot.outreach.purpose import PURPOSE_CHANNELS
    used = set()
    for chans in PURPOSE_CHANNELS.values():
        used.update(chans)
    assert used.issubset(set(CONTENT_TYPE_CONFIGS.keys()))
```

- [ ] **Step 10.2: Run — expect failure**

Run: `uv run pytest tests/outreach/test_seed_senso.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 10.3: Implement seed script**

Create `scripts/seed_senso.py`:
```python
"""Idempotent Senso workspace seed.

Creates the content types required by the Outreach workflow if they do not
already exist in the workspace. Safe to re-run.

Usage:
    uv run python -m scripts.seed_senso
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python -m scripts.seed_senso` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS  # noqa: E402
from paperpilot.outreach.senso import Senso  # noqa: E402


def seed_content_types(senso: Senso) -> dict[str, str]:
    """Ensure every required content type exists. Returns name -> id map."""
    existing = {ct["name"]: ct["id"] for ct in senso.list_content_types()}
    ids: dict[str, str] = {}
    for name, config in CONTENT_TYPE_CONFIGS.items():
        if name in existing:
            ids[name] = existing[name]
            continue
        created = senso.create_content_type(name, config)
        ids[name] = created["id"]
    return ids


def main() -> None:
    senso = Senso.from_env()
    ids = seed_content_types(senso)
    print("Senso content types ready:")
    for name, ctid in ids.items():
        print(f"  {name:30s} -> {ctid}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 10.4: Run — expect pass**

Run: `uv run pytest tests/outreach/test_seed_senso.py -v`
Expected: 3 passed.

- [ ] **Step 10.5: Commit**

```bash
git add paperpilot/outreach/content_types.py scripts/seed_senso.py tests/outreach/test_seed_senso.py
git commit -m "outreach: content_types module + idempotent Senso seed script"
```

---

## Task 11: Orchestrator — generate_drafts

**Files:**
- Create: `paperpilot/outreach/orchestrator.py`
- Create: `tests/outreach/test_orchestrator.py`

- [ ] **Step 11.1: Write failing test**

Create `tests/outreach/test_orchestrator.py`:
```python
from unittest.mock import MagicMock

from paperpilot.outreach.orchestrator import generate_drafts, DraftCard
from paperpilot.outreach.purpose import Purpose


def test_generate_drafts_returns_one_card_per_channel():
    senso = MagicMock()
    senso.get_or_create_content_type.side_effect = lambda name, cfg: f"ct-{name}"
    senso.generate_sample.side_effect = lambda content_type_id, context: f"job-{content_type_id}"
    senso.poll_until_done.side_effect = lambda jid, **kw: {
        "status": "completed",
        "result": {
            "raw_markdown": f"draft for {jid}",
            "content_id": f"d-{jid}",
        },
    }

    cards = generate_drafts(
        senso=senso,
        purpose=Purpose.BRAND,
        context="ML4H paper on retrieval calibration",
        session_id="sess_test",
        logger=MagicMock(),
    )

    assert [c.channel for c in cards] == ["linkedin_post_brand", "x_thread_brand"]
    assert all(isinstance(c, DraftCard) for c in cards)
    assert all(c.markdown.startswith("draft for job-ct-") for c in cards)
    assert all(c.sample_job_id.startswith("job-ct-") for c in cards)


def test_generate_drafts_continues_when_one_channel_fails():
    senso = MagicMock()
    senso.get_or_create_content_type.side_effect = lambda name, cfg: f"ct-{name}"

    def gen(content_type_id, context):
        if "x_thread" in content_type_id:
            raise RuntimeError("simulated failure")
        return f"job-{content_type_id}"

    senso.generate_sample.side_effect = gen
    senso.poll_until_done.side_effect = lambda jid, **kw: {
        "status": "completed",
        "result": {"raw_markdown": f"draft for {jid}", "content_id": "d"},
    }

    cards = generate_drafts(
        senso=senso,
        purpose=Purpose.BRAND,
        context="ctx",
        session_id="sess_test",
        logger=MagicMock(),
    )

    # 1 success (linkedin) + 1 error card (x_thread)
    assert len(cards) == 2
    assert cards[0].error is None
    assert cards[1].error is not None
    assert cards[1].markdown == ""
```

- [ ] **Step 11.2: Run — expect failure**

Run: `uv run pytest tests/outreach/test_orchestrator.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 11.3: Implement orchestrator**

Create `paperpilot/outreach/orchestrator.py`:
```python
"""Outreach orchestrator: purpose -> Senso draft cards.

Wraps every Senso call in `paperpilot.trace.step` so the existing Lapdog
pipeline captures each step into Datadog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperpilot import trace
from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS
from paperpilot.outreach.purpose import Purpose, channels_for
from paperpilot.outreach.senso import Senso


@dataclass
class DraftCard:
    channel: str
    content_type_id: str
    sample_job_id: str
    markdown: str
    draft_id: str = ""
    error: str | None = None


def _build_context(purpose: Purpose, user_context: str) -> str:
    purpose_blurbs = {
        Purpose.VISA: (
            "Audience: conference organizers, journal editors, and selection "
            "committees evaluating extraordinary-ability candidates."
        ),
        Purpose.CAREER: (
            "Audience: a peer or senior whose work overlaps yours, "
            "approached for networking or mentorship."
        ),
        Purpose.BRAND: (
            "Audience: your professional network. Build credibility around "
            "the topic below; do not pitch a product."
        ),
        Purpose.SERVICE: (
            "Audience: prospective clients who might pay for the service/"
            "product described below. Value-first; one CTA."
        ),
    }
    return f"{purpose_blurbs[purpose]}\n\nContext from the author:\n{user_context}"


def generate_drafts(
    senso: Senso,
    purpose: Purpose | str,
    context: str,
    session_id: str,
    logger: Any | None = None,
) -> list[DraftCard]:
    """Generate one draft card per channel mapped to `purpose`.

    `logger` is an `outreach.log` module reference or any object exposing
    `log_generate(...)`. Passing it explicitly keeps the function testable.
    """
    if isinstance(purpose, str):
        purpose = Purpose(purpose)

    full_context = _build_context(purpose, context)
    cards: list[DraftCard] = []

    for channel in channels_for(purpose):
        ct_config = CONTENT_TYPE_CONFIGS.get(channel, {"template": ""})
        with trace.step(
            session_id,
            "senso.generate",
            purpose=purpose.value,
            channel=channel,
        ) as ctx:
            try:
                ct_id = senso.get_or_create_content_type(channel, ct_config)
                ctx["content_type_id"] = ct_id
                job_id = senso.generate_sample(ct_id, full_context)
                ctx["job_id"] = job_id
                job = senso.poll_until_done(job_id, timeout_s=30.0, interval_s=1.0)
                md = job.get("result", {}).get("raw_markdown", "")
                draft_id = job.get("result", {}).get("content_id", "")
                ctx["draft_chars"] = len(md)
                if logger is not None:
                    logger.log_generate(
                        user_id="demo",
                        purpose=purpose.value,
                        channel=channel,
                        content_type_id=ct_id,
                        sample_job_id=job_id,
                    )
                cards.append(DraftCard(
                    channel=channel,
                    content_type_id=ct_id,
                    sample_job_id=job_id,
                    markdown=md,
                    draft_id=draft_id,
                ))
            except Exception as exc:  # noqa: BLE001 -- demo path
                ctx["error"] = str(exc)
                cards.append(DraftCard(
                    channel=channel,
                    content_type_id="",
                    sample_job_id="",
                    markdown="",
                    error=str(exc),
                ))
    return cards
```

- [ ] **Step 11.4: Run — expect pass**

Run: `uv run pytest tests/outreach/test_orchestrator.py -v`
Expected: 2 passed.

- [ ] **Step 11.5: Run full suite**

Run: `uv run pytest -v`
Expected: all tests pass (33+ collectively across tasks 2-11).

- [ ] **Step 11.6: Commit**

```bash
git add paperpilot/outreach/orchestrator.py tests/outreach/test_orchestrator.py
git commit -m "outreach: orchestrator — purpose -> Senso drafts, traced + logged"
```

---

## Task 12: Streamlit "Brand" tab

**Files:**
- Modify: `app.py` (add a new tab; the rest of the app is untouched)

- [ ] **Step 12.1: Inspect the current tab structure**

Run: `grep -n "st.tabs\|st.sidebar\|st.session_state" /Users/nikkihu/Documents/Github/agentichack/app.py | head -30`
Find the existing `st.tabs([...])` call. You will add three tab labels.

- [ ] **Step 12.2: Wire the Brand tab**

Inside the existing `st.tabs([...])` call, append three labels: `"Brand"`, `"Outreach"`, `"Track"`. Then add a new section at the bottom of `app.py` (after the existing tab implementations) using the new tab handles. For the Brand tab, paste this exact code:

```python
# ----- Outreach: Brand tab -----
with tab_brand:
    import os
    from paperpilot.outreach.log import UserProfile, upsert_user_profile
    from paperpilot.outreach.senso import Senso, SensoAPIError

    st.subheader("Your Brand on Senso")
    st.caption("Synced to workspace **Agentic-hack** at apiv2.senso.ai")

    col_l, col_r = st.columns(2)
    name = col_l.text_input("Name", value=st.session_state.get("brand_name", ""))
    title = col_r.text_input("Title", value=st.session_state.get("brand_title", ""))
    about = st.text_area(
        "About",
        value=st.session_state.get("brand_about", ""),
        height=120,
    )
    voice = st.text_area(
        "Voice & tone",
        value=st.session_state.get("brand_voice", ""),
        placeholder="e.g. warm, evidence-based, jargon-free",
        height=80,
    )

    st.markdown("**Links**")
    c1, c2 = st.columns(2)
    github_url   = c1.text_input("GitHub",   value=st.session_state.get("brand_github", ""))
    linkedin_url = c2.text_input("LinkedIn", value=st.session_state.get("brand_linkedin", ""))
    c3, c4 = st.columns(2)
    scholar_url  = c3.text_input("Google Scholar", value=st.session_state.get("brand_scholar", ""))
    site_url     = c4.text_input("Site",     value=st.session_state.get("brand_site", ""))

    resume_text = st.text_area(
        "Resume (paste contents)",
        value=st.session_state.get("brand_resume", ""),
        height=160,
    )

    if st.button("Sync to Senso", type="primary"):
        if not os.environ.get("SENSO_API_KEY"):
            st.error("SENSO_API_KEY not set. Add it to .env and restart.")
        else:
            payload = {
                "brand_name": name,
                "brand_description": f"{about}\n\n{resume_text}".strip(),
                "voice_and_tone": voice,
                "guidelines": {
                    "title": title,
                    "links": {
                        "github":   github_url,
                        "linkedin": linkedin_url,
                        "scholar":  scholar_url,
                        "site":     site_url,
                    },
                },
            }
            try:
                Senso.from_env().put_brand_kit(payload)
                st.success("Synced to Senso ✓")
            except SensoAPIError as e:
                st.error(f"Senso error: {e}")

            # Mirror into ClickHouse user_profile (best-effort).
            try:
                upsert_user_profile(UserProfile(
                    user_id="demo",
                    name=name, title=title, about=about, voice_tone=voice,
                    github_url=github_url, linkedin_url=linkedin_url,
                    scholar_url=scholar_url, site_url=site_url,
                    resume_text=resume_text,
                ))
            except Exception as e:  # noqa: BLE001
                st.caption(f"(ClickHouse mirror skipped: {e})")
```

The variable `tab_brand` should be unpacked from the `st.tabs(...)` call alongside the existing tabs. Adjust the unpack to: `tab_paper, tab_phase1, tab_brand, tab_outreach, tab_track = st.tabs([...])` (rename the existing handles in your code to match — keep the existing tab names).

- [ ] **Step 12.3: Smoke test**

Run: `make dev`
Open `http://localhost:8501`. Click the **Brand** tab. Fill 3 fields. Click **Sync to Senso**. Without an API key, you should see the "SENSO_API_KEY not set" error. With a key set, you should see "Synced ✓" (or a Senso error message, never a stack trace).

- [ ] **Step 12.4: Commit**

```bash
git add app.py
git commit -m "outreach: app.py Brand tab — Senso brand-kit sync + CH mirror"
```

---

## Task 13: Streamlit "Outreach" tab

**Files:**
- Modify: `app.py` (the Outreach tab section)

- [ ] **Step 13.1: Wire the Outreach tab**

Append this code to `app.py` right after the Brand tab section:

```python
# ----- Outreach: Generate tab -----
with tab_outreach:
    import os
    from paperpilot import trace
    from paperpilot.outreach import log as outreach_log
    from paperpilot.outreach.orchestrator import generate_drafts
    from paperpilot.outreach.purpose import Purpose
    from paperpilot.outreach.senso import Senso

    st.subheader("Outreach Drafts")
    st.caption("Drafts powered by Senso. Pick a purpose; we ship the cards.")

    purpose_label = st.radio(
        "Purpose",
        options=[p.value for p in Purpose],
        horizontal=True,
        captions=[
            "Extraordinary-ability dossier (O-1)",
            "Networking / mentorship",
            "Personal brand building",
            "Sell a service or product",
        ],
    )
    user_ctx = st.text_area(
        "What's this about?",
        placeholder="e.g. I want to apply to keynote at ML4H 2026.",
        height=100,
    )

    if st.button("Generate", type="primary", disabled=not user_ctx.strip()):
        if not os.environ.get("SENSO_API_KEY"):
            st.error("SENSO_API_KEY not set. Add it to .env and restart.")
        else:
            sid = st.session_state.get("outreach_sid") or trace.new_session()
            st.session_state["outreach_sid"] = sid
            with st.spinner("Drafting via Senso..."):
                cards = generate_drafts(
                    senso=Senso.from_env(),
                    purpose=purpose_label,
                    context=user_ctx,
                    session_id=sid,
                    logger=outreach_log,
                )
            st.session_state["outreach_cards"] = cards

    cards = st.session_state.get("outreach_cards", [])
    for i, card in enumerate(cards):
        st.markdown(f"### {card.channel}")
        if card.error:
            st.error(f"Generation failed: {card.error}")
            continue
        edited = st.text_area(
            "Draft",
            value=card.markdown,
            key=f"draft_{i}_{card.sample_job_id}",
            height=240,
        )
        c1, c2 = st.columns([1, 1])
        if c1.button("Copy", key=f"copy_{i}"):
            st.toast("Copied to clipboard (demo)")
        if c2.button(f"Post to {card.channel.split('_')[0]}", key=f"post_{i}"):
            try:
                outreach_log.mark_posted(
                    sample_job_id=card.sample_job_id,
                    draft_id=card.draft_id,
                )
            except Exception:
                pass  # CH mirror is best-effort
            st.toast(f"Posted to {card.channel} ✓ (demo)")
```

- [ ] **Step 13.2: Smoke test**

Run: `make dev`. Pick `BRAND`, type "I just shipped PaperPilot — a tool that turns a GitHub repo into a research paper draft.", click Generate. Expect two cards within ~30s (linkedin_post_brand + x_thread_brand) with real Senso markdown.

If Senso returns a `geo_question_id` required error (see spec §16 risk row), update `Senso.generate_sample` to first POST to `/org/geo-questions` and pass that id instead of `context`. Re-run.

- [ ] **Step 13.3: Commit**

```bash
git add app.py
git commit -m "outreach: app.py Outreach tab — purpose picker + Senso draft cards"
```

---

## Task 14: Streamlit "Track" tab

**Files:**
- Modify: `app.py` (the Track tab section)

- [ ] **Step 14.1: Wire the Track tab**

Append to `app.py`:

```python
# ----- Outreach: Track tab -----
with tab_track:
    import os
    import pandas as pd
    from paperpilot.outreach import log as outreach_log
    from paperpilot.outreach.scholar import fetch_mock, O1_THRESHOLD
    from paperpilot.outreach.senso import Senso, SensoAPIError

    st.subheader("Visa Progress Dashboard")

    scholar = fetch_mock()
    try:
        posted = outreach_log.count_posted("demo")
    except Exception:
        posted = 0

    senso_owned_total = 0
    senso_external_total = 0
    if os.environ.get("SENSO_API_KEY"):
        try:
            s = Senso.from_env()
            senso_owned_total = s.citation_trends("owned").get("total", 0)
            senso_external_total = s.citation_trends("external").get("total", 0)
        except SensoAPIError:
            pass

    # Composite "Extraordinary Ability score" (UX flavor).
    score = (
        0.4 * min(scholar.total_citations / O1_THRESHOLD, 1.0)
        + 0.3 * min((senso_owned_total + senso_external_total) / 100.0, 1.0)
        + 0.3 * min(posted / 25.0, 1.0)
    ) * 100

    st.metric("Extraordinary Ability score", f"{score:.0f} / 100")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("**Academic citations (Scholar)**")
        st.metric(
            f"{scholar.total_citations} / {O1_THRESHOLD}",
            f"h-index {scholar.h_index}",
        )
        st.progress(scholar.progress_to_o1())
        df = pd.DataFrame(scholar.by_month)
        st.line_chart(df, x="date", y="count", height=160)
        st.caption("≥20 citations is widely cited as the O-1 threshold.")

    with col_b:
        st.markdown("**AI citations (Senso)**")
        st.metric("Owned", senso_owned_total)
        st.metric("External", senso_external_total)
        st.caption("How often ChatGPT, Perplexity, Claude cite your work.")

    with col_c:
        st.markdown("**Drafts published**")
        st.metric("This workspace", posted)
        if os.environ.get("SENSO_API_KEY"):
            try:
                drafts = Senso.from_env().list_drafts(limit=5)
                for d in drafts:
                    title = (d.get("seo_title") or d.get("raw_markdown") or "")[:80]
                    st.write(f"- {title}")
            except SensoAPIError:
                pass
```

- [ ] **Step 14.2: Smoke test**

Run: `make dev`. Click **Track**. Verify all three columns render. Without `SENSO_API_KEY` the AI-citations column shows zeros (no crash). The Scholar tile must show `14 / 20` and a line chart climbing.

- [ ] **Step 14.3: Commit**

```bash
git add app.py
git commit -m "outreach: app.py Track tab — Scholar + Senso citation tiles + composite score"
```

---

## Task 15: Makefile + demo rehearsal checklist

**Files:**
- Modify: `Makefile`

- [ ] **Step 15.1: Add three targets**

Append to `Makefile`:
```makefile
test:
	uv run pytest -q

seed-senso:
	uv run python -m scripts.seed_senso

outreach-demo:
	@echo "Outreach demo rehearsal:"
	@echo "  1. Brand tab: confirm pre-synced brand kit for 'Nikki' loads."
	@echo "  2. Outreach tab: pick VISA, type 'apply to keynote at ML4H 2026', Generate."
	@echo "  3. Track tab: confirm score, Scholar climbs to 14/20, drafts list shows."
	@echo ""
	@echo "If anything 500s, fall back to: DEMO_MODE=true make dev."
```

- [ ] **Step 15.2: Run the full test suite once**

Run: `uv run pytest -q`
Expected: all tests pass. Note the total count.

- [ ] **Step 15.3: Run seed (if you have a key already)**

If `SENSO_API_KEY` is set in `.env`: `make seed-senso`
Expected: prints `Senso content types ready:` followed by 6 name -> id lines.

- [ ] **Step 15.4: End-to-end smoke**

Run: `make dev`
Click through all three tabs in the order from the rehearsal output. Take a screenshot of the Track tab for the pitch.

- [ ] **Step 15.5: Commit**

```bash
git add Makefile
git commit -m "outreach: Makefile targets — test, seed-senso, outreach-demo"
```

---

## Self-review checklist (post-implementation)

- [ ] Every Senso method has at least one test with mocked HTTP.
- [ ] `paperpilot/outreach/` has no `requests` import outside `senso.py`.
- [ ] No `print()` or `breakpoint()` left in the package code.
- [ ] `make test` passes from a clean checkout (`uv sync --dev && make test`).
- [ ] App boots cleanly with and without `SENSO_API_KEY`.
- [ ] Composite score formula in Track tab matches the spec §7 Panel A formula exactly.
- [ ] `outreach_log` has at least one `posted=1` row after the smoke test (so Track shows `1` instead of `0` for "Drafts published").
