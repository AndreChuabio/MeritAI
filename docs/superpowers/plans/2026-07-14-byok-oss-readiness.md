# Merit BYOK + Open-Source Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Merit safe to open-source and able to run on other people's API keys, with no billing, no vendor lock-in, and no key custody.

**Architecture:** `paperpilot/gateway.py:get_client()` is the single chokepoint for every LLM call in the codebase, so BYOK becomes a request-scoped `ContextVar` read by that one function rather than a key threaded through nine call sites. `paperpilot/trace.py` already computes per-call cost and discards it into an unconfigured ClickHouse; repointing it at the existing `supabase_client.insert_trace` turns it into the usage ledger that quotas depend on. Market's Senso dependency is replaced by a direct LLM call built from the `CONTENT_TYPE_CONFIGS` templates that already exist.

**Tech Stack:** Python 3.12, FastAPI, Supabase Postgres (psycopg), OpenAI SDK against Vercel AI Gateway, pytest, Next.js 16 frontend.

## Global Constraints

- **BYOK key type is a Vercel AI Gateway key, not a provider key.** Merit calls three providers (`google/gemini-2.5-flash` for ingest, `anthropic/claude-sonnet-4-6` for draft, `openai/text-embedding-3-small` for embed — `paperpilot/gateway.py:35-39`). No single provider key can run the pipeline. The gateway abstraction is what makes one user key sufficient.
- **User API keys are never persisted.** Not in a table, not in a log, not in a trace payload, not in an error message, not returned in a response body. Held in the browser, sent per request, used transiently.
- **Quotas are enforced in FastAPI, never in the Next.js client.** The backend connects to Supabase as service role and bypasses RLS; anything enforced only in the UI is enforced nowhere.
- **No billing code.** No Stripe, no plans, no entitlements, no `price_id`. If a task seems to want one, the task is wrong.
- **No emojis and no exclamation marks** in code, comments, docs, or commit messages.
- Run tests with `make test` (pytest, `testpaths = ["tests"]`, `pythonpath = ["."]`).
- The internal Python package stays named `paperpilot`. Do not rename it. The user-facing brand is Merit.

---

### Task 1: Fail the dev-auth fallback closed

The legacy Streamlit passcode shim falls back to a built-in `dev`/`dev` account when `PAPERPILOT_USERS_JSON` is unset. Once the repo is public, that fallback passcode is public, and any deployed instance that loses the env var becomes world-accessible with a known password.

**Files:**
- Modify: `paperpilot/auth.py:44-64`
- Test: `tests/test_auth_fallback.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `paperpilot.auth._load_users() -> tuple[list[_UserRecord], bool]` keeps its signature. Behaviour change only: it returns `([], True)` instead of a dev user unless `ALLOW_DEV_AUTH=1`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_fallback.py
"""The dev-auth fallback must fail closed once the repo is public."""

import pytest

from paperpilot import auth


def test_no_users_configured_yields_no_users(monkeypatch):
    """Unset PAPERPILOT_USERS_JSON grants no access, not a dev account."""
    monkeypatch.delenv("PAPERPILOT_USERS_JSON", raising=False)
    monkeypatch.delenv("ALLOW_DEV_AUTH", raising=False)
    users, is_fallback = auth._load_users()
    assert users == []
    assert is_fallback is True


def test_malformed_json_yields_no_users(monkeypatch):
    """Malformed config must not silently downgrade to the dev account."""
    monkeypatch.setenv("PAPERPILOT_USERS_JSON", "{not json")
    monkeypatch.delenv("ALLOW_DEV_AUTH", raising=False)
    users, is_fallback = auth._load_users()
    assert users == []
    assert is_fallback is True


def test_dev_user_requires_explicit_opt_in(monkeypatch):
    """The dev account is available only with ALLOW_DEV_AUTH=1."""
    monkeypatch.delenv("PAPERPILOT_USERS_JSON", raising=False)
    monkeypatch.setenv("ALLOW_DEV_AUTH", "1")
    users, is_fallback = auth._load_users()
    assert len(users) == 1
    assert users[0]["user_id"] == "dev"
    assert is_fallback is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_fallback.py -v`
Expected: FAIL — `test_no_users_configured_yields_no_users` asserts `users == []` but gets one dev record.

- [ ] **Step 3: Write minimal implementation**

Replace `paperpilot/auth.py:44-45` and the fallback returns inside `_load_users`:

```python
_DEV_USER: _UserRecord = {"user_id": "dev", "name": "Dev", "passcode": "dev"}
_USERS_ENV_VAR = "PAPERPILOT_USERS_JSON"
_DEV_AUTH_ENV_VAR = "ALLOW_DEV_AUTH"


def _dev_fallback() -> tuple[List[_UserRecord], bool]:
    """Return the fallback user set.

    Fails closed by default: an unconfigured instance grants access to nobody.
    The built-in dev account is available only when ALLOW_DEV_AUTH=1 is set
    explicitly, so a public deployment that loses PAPERPILOT_USERS_JSON does not
    silently become accessible with a passcode that anyone can read in the repo.
    """
    if os.environ.get(_DEV_AUTH_ENV_VAR) == "1":
        return [dict(_DEV_USER)], True  # type: ignore[list-item]
    logger.warning(
        "%s is unset and %s is not 1: refusing all logins.",
        _USERS_ENV_VAR,
        _DEV_AUTH_ENV_VAR,
    )
    return [], True
```

Then replace every `return [dict(_DEV_USER)], True` inside `_load_users` with `return _dev_fallback()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth_fallback.py -v && make test`
Expected: 3 passed in the new file; the full suite still passes.

- [ ] **Step 5: Commit**

```bash
git add paperpilot/auth.py tests/test_auth_fallback.py
git commit -m "Fail the dev-auth fallback closed

The built-in dev/dev account becomes public knowledge the moment the repo is
public. An instance that loses PAPERPILOT_USERS_JSON must refuse all logins
rather than accept a passcode anyone can read. ALLOW_DEV_AUTH=1 opts back in."
```

---

### Task 2: Remove the real name from fabricated seed data

`data/scholar_seed.json` presents a real person as the author of invented papers with a `?user=DEMO` scholar URL. That cannot go public without her consent.

**Files:**
- Modify: `data/scholar_seed.json`
- Test: `tests/test_seed_data.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Data-only change.

- [ ] **Step 1: Read the file to see the real shape before editing**

Run: `cat data/scholar_seed.json`

Note the exact key names. The test below asserts against a name field; if the schema differs, keep the assertion and adapt the key.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_seed_data.py
"""Public seed data must not attribute fabricated work to real people."""

import json
from pathlib import Path

# Real people whose names must never appear in demo/fixture data that ships
# publicly. Fabricated citations attached to a real name are a defamation and
# consent problem, not a styling one.
REAL_NAMES = {"Nikki Hu", "Andre Chuabio"}


def test_scholar_seed_names_no_real_people():
    raw = Path("data/scholar_seed.json").read_text()
    for name in REAL_NAMES:
        assert name not in raw, (
            f"{name!r} appears in data/scholar_seed.json, which ships publicly "
            "and contains fabricated citations."
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_seed_data.py -v`
Expected: FAIL — "Nikki Hu" appears in `data/scholar_seed.json`.

- [ ] **Step 4: Replace the name**

Edit `data/scholar_seed.json` and replace the `"name"` value `"Nikki Hu"` with `"Ada Lovelace"` (a public-domain figure already used elsewhere in the repo's placeholder emails). Change no other field.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_seed_data.py -v && make test`
Expected: PASS, and the full suite still passes.

- [ ] **Step 6: Commit**

```bash
git add data/scholar_seed.json tests/test_seed_data.py
git commit -m "Use a fictional name in scholar seed data

The seed fixture attributed invented papers and a DEMO scholar URL to a real
person. Guard it with a test so it cannot regress before the repo goes public."
```

---

### Task 3: Repoint the trace ledger at Supabase

`trace.py:22` imports `insert_trace` from ClickHouse and `trace.py:79-80` returns early whenever `CLICKHOUSE_HOST` is unset — which it is in production. Every cost figure the code computes is thrown away. `paperpilot/supabase_client.py:106` already exposes an `insert_trace` with a compatible signature.

**Files:**
- Modify: `paperpilot/trace.py:22,31-32,70-86`
- Test: `tests/test_trace_ledger.py` (create)

**Interfaces:**
- Consumes: `paperpilot.supabase_client.insert_trace(session_id: str, user_id: str | None, kind: str, payload: dict, conn=None) -> None`.
- Produces: `paperpilot.trace.log_event(session_id, kind, payload)` now writes to Supabase `trace_log` when `SUPABASE_DB_URL` is set. `trace.step(...)` is unchanged in signature.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trace_ledger.py
"""trace.log_event must write to Supabase, not a dead ClickHouse import."""

from paperpilot import trace


def test_log_event_writes_to_supabase(monkeypatch):
    """With SUPABASE_DB_URL set, events reach supabase_client.insert_trace."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    calls = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: calls.append(
            (session_id, user_id, kind, payload)
        ),
    )
    sid = trace.new_session("11111111-1111-1111-1111-111111111111")
    trace.log_event(sid, "test.kind", {"cost_usd": 0.01})

    assert len(calls) == 1
    assert calls[0][0] == sid
    assert calls[0][1] == "11111111-1111-1111-1111-111111111111"
    assert calls[0][2] == "test.kind"
    assert calls[0][3]["cost_usd"] == 0.01


def test_empty_user_id_becomes_null(monkeypatch):
    """A session with no bound user writes NULL, not '', into a uuid column."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    calls = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: calls.append(user_id),
    )
    trace.log_event("sess_orphan", "test.kind", {})
    assert calls == [None]


def test_no_supabase_configured_is_a_noop(monkeypatch):
    """Unconfigured instances buffer in memory and never raise."""
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)

    def explode(*args, **kwargs):
        raise AssertionError("must not write when unconfigured")

    monkeypatch.setattr(trace, "insert_trace", explode)
    trace.log_event("sess_x", "test.kind", {})
    assert trace.buffered_events("sess_x")[-1].kind == "test.kind"


def test_insert_failure_never_raises(monkeypatch):
    """A ledger write failure must not fail the user's run."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(trace, "insert_trace", boom)
    trace.log_event("sess_y", "test.kind", {})
    evt = trace.buffered_events("sess_y")[-1]
    assert any("trace_insert_failed" in w for w in evt.payload["_warn"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_trace_ledger.py -v`
Expected: FAIL — `trace` has no attribute `insert_trace` pointing at Supabase; the module imports the ClickHouse one and gates on `CLICKHOUSE_HOST`.

- [ ] **Step 3: Write the implementation**

In `paperpilot/trace.py`, replace the import at line 22:

```python
from paperpilot.supabase_client import insert_trace
```

Replace `_clickhouse_configured` (lines 31-32) with:

```python
def _ledger_configured() -> bool:
    """True when a Supabase connection string is available to write traces to."""
    return bool(os.environ.get("SUPABASE_DB_URL"))
```

Replace the body of `log_event` (lines 77-86) with:

```python
    evt = TraceEvent(session_id=session_id, ts=time(), kind=kind, payload=payload)
    _BUFFER.setdefault(session_id, []).append(evt)
    if not _ledger_configured():
        return
    # trace_log.user_id is a uuid column: an unbound session must write NULL,
    # not the empty string, or the insert fails on the cast.
    user_id = _SESSION_USER.get(session_id) or None
    try:
        insert_trace(session_id, user_id, kind, payload)
    except Exception as exc:  # noqa: BLE001 -- best-effort; never fail the run
        evt.payload.setdefault("_warn", []).append(f"trace_insert_failed: {exc!s}")
```

Update the module docstring's first paragraph to say rows land in Supabase `trace_log` rather than ClickHouse.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_trace_ledger.py -v && make test`
Expected: 4 passed; full suite green.

- [ ] **Step 5: Commit**

```bash
git add paperpilot/trace.py tests/test_trace_ledger.py
git commit -m "Write the trace ledger to Supabase instead of a dead ClickHouse path

trace.step already computed tokens and cost_usd on every LLM call and then
dropped them, because the ClickHouse sink no-ops when CLICKHOUSE_HOST is unset,
which it is in production. Quotas and cost visibility both depend on this."
```

---

### Task 4: Make per-user cost queryable

Task 3 makes the rows land. This makes them answer a question.

**Files:**
- Modify: `paperpilot/supabase_client.py` (append a new function)
- Test: `tests/test_cost_query.py` (create)

**Interfaces:**
- Consumes: `trace_log(session_id text, user_id uuid, ts timestamptz, kind text, payload jsonb)` from `supabase/migrations/20260616161439_initial_schema.sql:49-56`.
- Produces: `paperpilot.supabase_client.user_cost_usd(user_id: str, since: datetime | None = None, conn=None) -> float` and `paperpilot.supabase_client.user_event_count(user_id: str, kind_prefix: str, since: datetime, conn=None) -> int`. Task 10 consumes `user_event_count` for quota enforcement.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cost_query.py
"""Cost and quota queries read the trace ledger."""

import inspect

from paperpilot import supabase_client


def test_user_cost_usd_exists_with_expected_signature():
    sig = inspect.signature(supabase_client.user_cost_usd)
    assert list(sig.parameters) == ["user_id", "since", "conn"]


def test_user_event_count_exists_with_expected_signature():
    sig = inspect.signature(supabase_client.user_event_count)
    assert list(sig.parameters) == ["user_id", "kind_prefix", "since", "conn"]


def test_user_cost_usd_sums_payload_cost(monkeypatch):
    """The query sums payload->>'cost_usd' for one user."""
    captured = {}

    class FakeCursor:
        def fetchone(self):
            return (0.42,)

    class FakeConn:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(supabase_client, "get_conn", lambda: FakeConn())
    total = supabase_client.user_cost_usd("user-1")
    assert total == 0.42
    assert "cost_usd" in captured["sql"]
    assert captured["params"][0] == "user-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cost_query.py -v`
Expected: FAIL — `module 'paperpilot.supabase_client' has no attribute 'user_cost_usd'`.

- [ ] **Step 3: Write the implementation**

Append to `paperpilot/supabase_client.py`:

```python
def user_cost_usd(
    user_id: str,
    since: datetime | None = None,
    conn: psycopg.Connection | None = None,
) -> float:
    """Total LLM spend attributed to one user, in USD.

    Reads cost_usd out of the trace_log payload written by paperpilot.trace.
    Events with no cost_usd (start events, non-LLM steps) contribute zero.
    """
    owns = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM((payload->>'cost_usd')::numeric), 0) "
            "FROM trace_log "
            "WHERE user_id = %s AND (%s IS NULL OR ts >= %s)",
            (user_id, since, since),
        ).fetchone()
        return float(row[0]) if row else 0.0
    finally:
        if owns:
            conn.close()


def user_event_count(
    user_id: str,
    kind_prefix: str,
    since: datetime,
    conn: psycopg.Connection | None = None,
) -> int:
    """Count a user's trace events of a given kind since a timestamp.

    Quota enforcement counts completed work, so callers should pass the
    '.end' suffix in kind_prefix (e.g. 'evidence_dossier') and this matches
    kind LIKE '<prefix>%.end'.
    """
    owns = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM trace_log "
            "WHERE user_id = %s AND kind LIKE %s AND ts >= %s",
            (user_id, f"{kind_prefix}%.end", since),
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        if owns:
            conn.close()
```

Ensure `from datetime import datetime` is already imported at the top of the module (it is — `insert_trace` uses `datetime.now()`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cost_query.py -v && make test`
Expected: 3 passed; full suite green.

- [ ] **Step 5: Commit**

```bash
git add paperpilot/supabase_client.py tests/test_cost_query.py
git commit -m "Add per-user cost and event-count queries over the trace ledger

Turns the ledger rows from Task 3 into the two questions the product needs to
answer: what has this user cost, and how many of X have they run this period."
```

---

### Task 5: BYOK — request-scoped LLM key

`gateway.get_client()` is the only place any LLM client is constructed for the Merit pipeline (callers: `paperpilot/embed.py:19,26`, `paperpilot/draft.py:220`, `paperpilot/llm_ingest.py:66`, `paperpilot/skill_extract.py:198`, `paperpilot/outreach/evidence_draft.py:233`, `backend/services/assist_service.py:120`, `backend/services/evidence_service.py:439`). Making it prefer a request-scoped key gives BYOK everywhere without touching those call sites.

**Files:**
- Modify: `paperpilot/gateway.py`
- Create: `backend/byok.py`
- Modify: `backend/routers/ingest.py`, `backend/routers/draft.py`, `backend/routers/plugin.py`, `backend/routers/market.py` (add the dependency to route signatures)
- Test: `tests/test_byok.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `paperpilot.gateway.set_request_key(key: str | None) -> None`
  - `paperpilot.gateway.get_client() -> OpenAI` (unchanged signature; now prefers the request key)
  - `backend.byok.RequireLLMKey` — a FastAPI dependency that reads the `X-LLM-Key` header, binds it for the request, and 400s when absent. Task 7 relies on it being applied to the market router.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_byok.py
"""A user-supplied gateway key is used for the request and never persisted."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.byok import RequireLLMKey
from paperpilot import gateway


@pytest.fixture(autouse=True)
def _clear_request_key():
    yield
    gateway.set_request_key(None)


def test_request_key_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "server-key")
    gateway.set_request_key("user-key")
    client = gateway.get_client()
    assert client.api_key == "user-key"


def test_falls_back_to_env_when_no_request_key(monkeypatch):
    """Track runs on Merit's key: no request key means use the server's."""
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "server-key")
    gateway.set_request_key(None)
    client = gateway.get_client()
    assert client.api_key == "server-key"


def test_raises_when_neither_key_present(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    gateway.set_request_key(None)
    with pytest.raises(RuntimeError, match="No LLM API key"):
        gateway.get_client()


def test_dependency_binds_header_key():
    app = FastAPI()

    @app.get("/probe")
    def probe(_: None = Depends(RequireLLMKey)) -> dict:
        return {"key": gateway.get_client().api_key}

    with TestClient(app) as client:
        resp = client.get("/probe", headers={"X-LLM-Key": "byok-abc"})
    assert resp.status_code == 200
    assert resp.json() == {"key": "byok-abc"}


def test_dependency_rejects_missing_header():
    app = FastAPI()

    @app.get("/probe")
    def probe(_: None = Depends(RequireLLMKey)) -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        resp = client.get("/probe")
    assert resp.status_code == 400
    assert "X-LLM-Key" in resp.json()["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_byok.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.byok'`.

- [ ] **Step 3: Implement the gateway change**

Rewrite `paperpilot/gateway.py:24-32`:

```python
from contextvars import ContextVar

# The caller's own gateway key, bound per request by backend.byok. A ContextVar
# rather than a parameter because get_client() has nine call sites across the
# pipeline and the key must not be threaded through all of them. Starlette runs
# each request in its own task, so each request gets its own context copy and
# keys cannot leak between concurrent callers.
_REQUEST_KEY: ContextVar[str | None] = ContextVar("merit_request_llm_key", default=None)


def set_request_key(key: str | None) -> None:
    """Bind (or clear) the caller's gateway key for the current request context."""
    _REQUEST_KEY.set(key or None)


def get_client() -> OpenAI:
    """Return an OpenAI client pointed at Vercel AI Gateway.

    Prefers the caller's own key when one is bound to this request (BYOK), and
    otherwise falls back to the server's key. Surfaces that run on Merit's dime
    (Track, the help assistant) bind nothing and get the server key; surfaces
    that run on the user's key (Productize, Market) bind theirs.
    """
    api_key = _REQUEST_KEY.get() or os.environ.get("AI_GATEWAY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No LLM API key available. Supply one via the X-LLM-Key header, or "
            "set AI_GATEWAY_API_KEY. Get a key at "
            "https://vercel.com/dashboard/ai-gateway"
        )
    return OpenAI(base_url=GATEWAY_BASE_URL, api_key=api_key)
```

- [ ] **Step 4: Implement the FastAPI dependency**

```python
# backend/byok.py
"""Bring-your-own-key: bind the caller's gateway key to this request.

Merit never stores a user's API key. The browser holds it, sends it on each
request in the X-LLM-Key header, and this dependency binds it to the request
context for the duration of the call. Nothing writes it to a table, a log, or a
response body. See backend/logging_filters.py for the scrubbing that enforces
the log half of that promise.

The key is a Vercel AI Gateway key, not a provider key: Merit calls Google for
ingest, Anthropic for drafting, and OpenAI for embeddings, so no single provider
key can run the pipeline.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from paperpilot import gateway


async def require_llm_key(
    x_llm_key: str | None = Header(default=None),
) -> None:
    """FastAPI dependency: bind the caller's gateway key, or reject the request."""
    if not x_llm_key or not x_llm_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This surface runs on your own API key. Supply a Vercel AI "
                "Gateway key in the X-LLM-Key header."
            ),
        )
    gateway.set_request_key(x_llm_key.strip())


RequireLLMKey = Depends(require_llm_key)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_byok.py -v`
Expected: 5 passed.

- [ ] **Step 6: Apply the dependency to the BYOK routers**

Add `_: None = RequireLLMKey` to the signature of every route that makes an LLM call on the user's behalf in `backend/routers/ingest.py`, `backend/routers/draft.py`, `backend/routers/plugin.py`, and the `/outreach/generate` route in `backend/routers/market.py:146-160`. Do **not** add it to `backend/routers/evidence.py` or `backend/routers/assist.py` — Track and the help assistant run on Merit's key.

Note `/match` also embeds (via `paperpilot/embed.py`), so the match route in `backend/main.py` needs it too.

Example, for the ingest route:

```python
from backend.byok import RequireLLMKey

@router.post("/ingest", response_model=IngestOut)
def ingest(
    body: IngestRequest,
    user: AuthUser = CurrentUser,
    _: None = RequireLLMKey,
) -> IngestOut:
    ...
```

- [ ] **Step 7: Run the full suite**

Run: `make test`
Expected: green. Existing backend tests that call these routes without the header will now 400 — update them to send `headers={"X-LLM-Key": "test-key"}`.

- [ ] **Step 8: Commit**

```bash
git add paperpilot/gateway.py backend/byok.py backend/routers/ backend/main.py tests/test_byok.py tests/backend/test_api.py
git commit -m "Add bring-your-own-key via a request-scoped gateway key

get_client() is the single chokepoint for every LLM call, so BYOK is a
ContextVar read there rather than a key threaded through nine call sites.
Productize and Market require the caller's key; Track and the assistant keep
running on the server key. The key is never persisted."
```

---

### Task 6: Prove the user's key never reaches a log

The promise in Task 5 is worthless without a test that enforces it. Three sinks can capture the key today: the FastAPI request path under `ddtrace-run`, Railway's platform logs, and `trace_log.payload` (a free-form `jsonb` column).

**Files:**
- Create: `paperpilot/redaction.py`
- Modify: `backend/main.py` (install the filter at startup)
- Modify: `paperpilot/trace.py` (scrub payloads before insert)
- Test: `tests/test_key_never_logged.py` (create)

**Interfaces:**
- Consumes: `paperpilot.gateway.set_request_key` from Task 5; `paperpilot.trace.log_event` from Task 3.
- Produces: `paperpilot.redaction.RedactKeyFilter` (a `logging.Filter`), `paperpilot.redaction.redact_text(str) -> str`, `paperpilot.redaction.SENSITIVE_KEYS`, `paperpilot.redaction.install() -> None`, and `paperpilot.trace._scrub(payload: dict) -> dict`.

**Note on placement:** redaction lives in `paperpilot`, not `backend`. `backend` imports `paperpilot` throughout, so putting it the other way round inverts the dependency and risks a circular import the moment `trace.py` needs it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_key_never_logged.py
"""The user's API key must not reach any log, trace, or database row."""

import logging

from paperpilot import trace
from paperpilot.redaction import RedactKeyFilter, SENSITIVE_KEYS

SECRET = "vck_super_secret_user_key"


def test_trace_payload_scrubs_sensitive_keys(monkeypatch):
    """A key accidentally passed into a trace payload is redacted before insert."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    written = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: written.append(payload),
    )
    sid = trace.new_session("11111111-1111-1111-1111-111111111111")
    trace.log_event(sid, "ingest.start", {"api_key": SECRET, "repo": "octocat/hello"})

    assert written[0]["api_key"] == "[REDACTED]"
    assert written[0]["repo"] == "octocat/hello"


def test_trace_payload_scrubs_nested(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://stub")
    written = []
    monkeypatch.setattr(
        trace,
        "insert_trace",
        lambda session_id, user_id, kind, payload: written.append(payload),
    )
    trace.log_event("s1", "k", {"headers": {"x-llm-key": SECRET}})
    assert written[0]["headers"]["x-llm-key"] == "[REDACTED]"


def test_log_filter_redacts_key_in_message():
    """A key that lands in a log message is redacted before it is emitted."""
    filt = RedactKeyFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="calling gateway with X-LLM-Key: %s",
        args=(SECRET,),
        exc_info=None,
    )
    filt.filter(record)
    assert SECRET not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_sensitive_key_names_cover_the_header():
    assert "x-llm-key" in SENSITIVE_KEYS
    assert "api_key" in SENSITIVE_KEYS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_key_never_logged.py -v`
Expected: FAIL — `No module named 'paperpilot.redaction'`.

- [ ] **Step 3: Implement the redaction filter**

```python
# paperpilot/redaction.py
"""Redaction of user-supplied secrets from anything that gets emitted.

Merit takes no custody of user API keys, which means a key must never survive
into a log line, a Datadog span, or a trace payload. This module is the single
definition of what counts as sensitive, used by both the logging filter and
paperpilot.trace's payload scrubber.

Lives in paperpilot rather than backend because paperpilot.trace needs it and
backend already depends on paperpilot -- the reverse would be circular.
"""

from __future__ import annotations

import logging
import re

REDACTED = "[REDACTED]"

# Field names whose values are secrets, lowercased for comparison.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "x-llm-key",
        "x_llm_key",
        "api_key",
        "apikey",
        "authorization",
        "ai_gateway_api_key",
        "senso_api_key",
        "nimble_api_key",
        "github_token",
        "supabase_service_role_key",
    }
)

# Value shapes that are secrets regardless of the field they appear in.
_SECRET_PATTERNS = [
    re.compile(r"vck_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
]


def redact_text(text: str) -> str:
    """Replace anything that looks like a credential in free text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class RedactKeyFilter(logging.Filter):
    """Strip credentials from log records before they are emitted anywhere."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 -- never break logging
            return True
        cleaned = redact_text(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def install() -> None:
    """Attach the redaction filter to the root logger and uvicorn's loggers."""
    filt = RedactKeyFilter()
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addFilter(filt)
```

- [ ] **Step 4: Implement the trace payload scrubber**

Add to `paperpilot/trace.py`, above `log_event`:

```python
from paperpilot.redaction import REDACTED, SENSITIVE_KEYS, redact_text


def _scrub(value: Any) -> Any:
    """Recursively redact credentials from a trace payload before it is stored.

    trace_log.payload is free-form jsonb; without this, a key passed into any
    step(...) kwarg would be persisted forever.
    """
    if isinstance(value, dict):
        return {
            k: (REDACTED if str(k).lower() in SENSITIVE_KEYS else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
```

Then in `log_event`, scrub before the insert:

```python
    try:
        insert_trace(session_id, user_id, kind, _scrub(payload))
```

Note the in-memory `_BUFFER` keeps the unscrubbed event, which is fine — it is process-local and never rendered to another user. Scrub at the persistence boundary only.

- [ ] **Step 5: Install the filter in the app**

In `backend/main.py`, immediately after `app = FastAPI(...)` (line 24):

```python
from paperpilot import redaction

redaction.install()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_key_never_logged.py -v && make test`
Expected: 4 passed; full suite green.

- [ ] **Step 7: Commit**

```bash
git add paperpilot/redaction.py backend/main.py paperpilot/trace.py tests/test_key_never_logged.py
git commit -m "Redact user API keys from logs and trace payloads

Taking no custody of a key is only true if the key cannot survive into a log
line or a jsonb payload. One definition of what is sensitive, enforced at both
the logging and the persistence boundary, with tests that assert it."
```

---

### Task 7: Un-vendor Market generation

`backend/services/market_service.py:283-294` returns an error card when `SENSO_API_KEY` is missing, and `paperpilot/outreach/orchestrator.py:86-91` delegates the entire generation to Senso. Nobody in the open-source audience has a Senso account, so the surface is broken on first run for almost everyone who clones the repo. The templates Senso was being handed already live in `paperpilot/outreach/content_types.py:12-81` — they are exactly what a direct LLM call needs.

**Files:**
- Create: `paperpilot/outreach/llm_draft.py`
- Modify: `paperpilot/outreach/orchestrator.py:56-118`
- Modify: `backend/services/market_service.py:267-311`
- Test: `tests/outreach/test_llm_draft.py` (create)

**Interfaces:**
- Consumes: `paperpilot.gateway.get_client` and `DEFAULTS` (Task 5); `CONTENT_TYPE_CONFIGS` from `paperpilot/outreach/content_types.py`; `channels_for` from `paperpilot/outreach/purpose.py:26`.
- Produces: `paperpilot.outreach.llm_draft.draft_channel(channel: str, full_context: str) -> str` returning markdown. `generate_drafts` keeps its `DraftCard` return type but its `senso` parameter becomes optional (`senso: Senso | None = None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/outreach/test_llm_draft.py
"""Outreach drafting works with an LLM key alone, no Senso account."""

import pytest

from paperpilot.outreach import llm_draft
from paperpilot.outreach.orchestrator import generate_drafts
from paperpilot.outreach.purpose import Purpose


class _FakeCompletions:
    def __init__(self, text):
        self._text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Msg:
            content = self._text

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _FakeClient:
    def __init__(self, text="drafted markdown"):
        self.chat = type("chat", (), {"completions": _FakeCompletions(text)})()


def test_draft_channel_builds_prompt_from_content_type(monkeypatch):
    """The channel's template and writing rules are what shape the prompt."""
    fake = _FakeClient()
    monkeypatch.setattr(llm_draft, "get_client", lambda: fake)

    out = llm_draft.draft_channel("linkedin_dm", "Audience: a peer.\n\nContext: x")

    assert out == "drafted markdown"
    prompt = fake.chat.completions.calls[0]["messages"][1]["content"]
    assert "under 600 chars" in prompt
    assert "End with one explicit ask." in prompt
    assert "Audience: a peer." in prompt


def test_generate_drafts_needs_no_senso(monkeypatch):
    """With senso=None, every channel still produces a card with markdown."""
    fake = _FakeClient("hello there")
    monkeypatch.setattr(llm_draft, "get_client", lambda: fake)

    cards = generate_drafts(
        senso=None,
        purpose=Purpose.NETWORK,
        context="I work on pgvector retrieval.",
        session_id="sess_test",
        user_id="11111111-1111-1111-1111-111111111111",
        logger=None,
    )

    # NETWORK maps to two channels in purpose.PURPOSE_CHANNELS.
    assert len(cards) == 2
    assert all(c.markdown == "hello there" for c in cards)
    assert all(c.error is None for c in cards)


def test_one_channel_failing_does_not_cancel_the_others(monkeypatch):
    """A failure is isolated to its own card, as before."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model unavailable")
        return _FakeClient("second one worked")

    monkeypatch.setattr(llm_draft, "get_client", flaky)

    cards = generate_drafts(
        senso=None,
        purpose=Purpose.NETWORK,
        context="ctx",
        session_id="sess_test",
        user_id="11111111-1111-1111-1111-111111111111",
        logger=None,
    )
    assert cards[0].error is not None
    assert cards[1].markdown == "second one worked"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/outreach/test_llm_draft.py -v`
Expected: FAIL — `No module named 'paperpilot.outreach.llm_draft'`.

- [ ] **Step 3: Implement the direct LLM drafter**

```python
# paperpilot/outreach/llm_draft.py
"""Draft one outreach message per channel with a direct LLM call.

Outreach generation used to route through Senso, which meant the surface
returned an error card for anyone without a Senso account -- that is, almost
everyone who clones this repo. The content-type templates Senso was being handed
are all the shaping a model needs, so we hand them to the model ourselves.

Senso remains supported as an optional enhancement (see orchestrator), but it is
no longer a precondition for getting a draft.
"""

from __future__ import annotations

from paperpilot.gateway import DEFAULTS, get_client
from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS

_SYSTEM_PROMPT = (
    "You are a writing assistant drafting professional outreach on behalf of "
    "the author described in the context. Write in the author's voice, in the "
    "first person. Be specific and concrete: reference the author's actual work "
    "rather than making generic claims. Never invent achievements, publications, "
    "affiliations, or metrics that are not present in the context. Output only "
    "the message itself, with no preamble and no commentary."
)


def _build_prompt(channel: str, full_context: str) -> str:
    """Compose the user prompt from the channel's template and writing rules."""
    config = CONTENT_TYPE_CONFIGS.get(channel, {})
    template = config.get("template", "")
    rules = config.get("writing_rules", [])
    rules_block = "\n".join(f"- {rule}" for rule in rules)
    return (
        f"Write the following:\n{template}\n\n"
        f"Rules you must follow:\n{rules_block}\n\n"
        f"{full_context}"
    )


def draft_channel(channel: str, full_context: str) -> str:
    """Return markdown for one outreach channel. Raises on model failure."""
    client = get_client()
    resp = client.chat.completions.create(
        model=DEFAULTS["draft"],
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(channel, full_context)},
        ],
        max_tokens=900,
        temperature=0.6,
    )
    return resp.choices[0].message.content or ""
```

- [ ] **Step 4: Rewrite the orchestrator's generation loop**

Replace `paperpilot/outreach/orchestrator.py:56-118`:

```python
def generate_drafts(
    senso: Senso | None,
    purpose: Purpose | str,
    context: str,
    session_id: str,
    user_id: str,
    logger: Any | None = None,
) -> list[DraftCard]:
    """Generate one draft card per channel mapped to `purpose`.

    `senso` is optional. When absent, drafting happens with a direct LLM call on
    the caller's own key, which is the path every open-source user takes. When
    present, Senso is used instead so its brand-kit tone retrieval still applies.

    `user_id` is the authed caller; required so outreach_log rows are scoped to
    the right user. `logger` is an `outreach.log` module reference or any object
    exposing `log_generate(...)`. Passing it explicitly keeps the function
    testable.
    """
    if isinstance(purpose, str):
        purpose = Purpose(purpose)

    full_context = _build_context(purpose, context)
    cards: list[DraftCard] = []

    for channel in channels_for(purpose):
        ct_config = CONTENT_TYPE_CONFIGS.get(channel, {"template": ""})
        backend_name = "senso.generate" if senso else "llm.generate"
        with trace.step(
            session_id,
            backend_name,
            purpose=purpose.value,
            channel=channel,
        ) as ctx:
            try:
                if senso is not None:
                    ct_id = senso.get_or_create_content_type(channel, ct_config)
                    ctx["content_type_id"] = ct_id
                    job_id = senso.generate_sample(ct_id, full_context)
                    ctx["job_id"] = job_id
                    job = senso.poll_until_done(job_id, timeout_s=30.0, interval_s=1.0)
                    md = job.get("result", {}).get("raw_markdown", "")
                    draft_id = job.get("result", {}).get("content_id", "")
                else:
                    ct_id = ""
                    job_id = ""
                    draft_id = ""
                    md = llm_draft.draft_channel(channel, full_context)

                ctx["draft_chars"] = len(md)
                if logger is not None:
                    logger.log_generate(
                        user_id=user_id,
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
            except Exception as exc:  # noqa: BLE001 -- one channel failing must not cancel the rest
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

Add the import at the top of `orchestrator.py`:

```python
from paperpilot.outreach import llm_draft
```

- [ ] **Step 5: Remove the Senso precondition from the service**

Replace `backend/services/market_service.py:283-308` — delete the `if not os.environ.get("SENSO_API_KEY")` early-return block entirely and make the Senso client optional:

```python
    # Senso is an optional enhancement, not a precondition. Without a key we
    # draft with a direct LLM call on the caller's own key, which is the path
    # every self-hosted user takes.
    senso = Senso.from_env() if os.environ.get("SENSO_API_KEY") else None

    session_id = trace.new_session(user_id)
    conn = supabase_client.get_conn()
    try:
        logger = _LogAdapter(conn)
        cards = generate_drafts(
            senso=senso,
            purpose=purpose_enum,
            context=context,
            session_id=session_id,
            user_id=user_id,
            logger=logger,
        )
    finally:
        conn.close()
    return [asdict(card) for card in cards]
```

Update the docstring on `generate_outreach` to drop the "Senso may be unconfigured / we return one error card" paragraph, replacing it with a note that Senso is optional.

Delete the now-unused `DraftCard` import in `market_service.py` if nothing else references it, and remove `asdict` only if unused (it is still used on the cards — keep it).

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/outreach/ -v && make test`
Expected: 3 new tests pass; the existing `tests/outreach/test_orchestrator.py` still passes (it passes a Senso stub, which remains supported).

- [ ] **Step 7: Commit**

```bash
git add paperpilot/outreach/llm_draft.py paperpilot/outreach/orchestrator.py backend/services/market_service.py tests/outreach/test_llm_draft.py
git commit -m "Un-vendor outreach drafting: direct LLM call, Senso optional

Market returned an error card for anyone without a SENSO_API_KEY, which is
nearly everyone who clones this repo. The content-type templates Senso was being
handed are all the shaping a model needs. Senso stays supported when a key is
present; without one, drafting runs on the caller's own key."
```

---

### Task 8: Degrade Nimble people-search gracefully

`backend/services/market_service.py:209-227` returns `configured: false` when `NIMBLE_API_KEY` is unset. That is already non-fatal, but the frontend presents it as a broken feature rather than an optional one. The user supplying the recipient themselves is the common case regardless.

**Files:**
- Modify: `backend/services/market_service.py:209-227`
- Modify: `web/app/(app)/market/page.tsx` (the people-search panel)
- Test: `tests/backend/test_market_optional_vendors.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the `/market/outreach/people` response gains a stable `reason: str` field alongside `configured: bool`, so the UI can explain rather than error.

- [ ] **Step 1: Read the current shape**

Run: `sed -n '200,235p' backend/services/market_service.py && grep -n "people" backend/routers/market.py`

Note the exact `PeopleResponse` model fields before changing them.

- [ ] **Step 2: Write the failing test**

```python
# tests/backend/test_market_optional_vendors.py
"""Missing vendor keys degrade the surface, they do not break it."""

from backend.services import market_service


def test_people_search_without_nimble_is_not_an_error(monkeypatch):
    """No Nimble key yields an explained empty result, not an exception."""
    monkeypatch.delenv("NIMBLE_API_KEY", raising=False)
    result = market_service.suggest_people(
        user_id="11111111-1111-1111-1111-111111111111",
        purpose="NETWORK",
        query="pgvector researchers",
    )
    assert result["configured"] is False
    assert result["people"] == []
    assert "enter the recipient" in result["reason"].lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/backend/test_market_optional_vendors.py -v`
Expected: FAIL — the response has no `reason` key.

- [ ] **Step 4: Add the reason field**

In `backend/services/market_service.py`, in the unconfigured branch of the people-search function, return:

```python
        return {
            "configured": False,
            "people": [],
            "reason": (
                "Contact discovery is an optional integration and is not "
                "configured. Enter the recipient's name and contact yourself to "
                "continue -- drafting works without it."
            ),
        }
```

Add `reason: str = ""` to the `PeopleResponse` model in `backend/routers/market.py`.

- [ ] **Step 5: Update the frontend copy**

In `web/app/(app)/market/page.tsx`, where the people-search panel currently renders a missing-key state as an error, render `reason` as an informational note beside a manual recipient input. Do not use an error style (red/destructive) for an optional integration.

- [ ] **Step 6: Run tests and the typecheck**

Run: `uv run pytest tests/backend/ -v && cd web && npx tsc --noEmit && cd ..`
Expected: tests pass, no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add backend/services/market_service.py backend/routers/market.py web/app/\(app\)/market/page.tsx tests/backend/test_market_optional_vendors.py
git commit -m "Present contact discovery as optional rather than broken

Nimble is an accelerant, not a precondition. Without a key the user types the
recipient in, which is the common case anyway. Say so instead of showing an
error."
```

---

### Task 9: Stop sending the repo bundle to Gemini twice

`/ingest` fetches the repo bundle (capped at 600K tokens by `paperpilot/github_ingest.py:26,29,188`) and sends it to Gemini. `/extract-plugin` then re-fetches and re-sends the same bundle (`paperpilot/skill_extract.py:198-205`). That doubles the cost of a Productize run. Even on the user's key, waste is a defect.

**Files:**
- Modify: `backend/services/ingest_service.py` (persist the bundle)
- Modify: `backend/services/plugin_service.py` (reuse it)
- Test: `tests/backend/test_bundle_reuse.py` (create)

**Interfaces:**
- Consumes: `paperpilot.supabase_client.insert_artifact` / `fetch_artifact_content` (already exist at `supabase_client.py:153,247`), and the `session_artifacts` table.
- Produces: ingest stores the bundle under artifact kind `repo_bundle` keyed by `session_id`; plugin extraction reads it and only re-fetches from GitHub when it is absent.

- [ ] **Step 1: Read both services to find the fetch call**

Run: `grep -n "bundle\|fetch_repo\|github_ingest" backend/services/ingest_service.py backend/services/plugin_service.py`

- [ ] **Step 2: Write the failing test**

```python
# tests/backend/test_bundle_reuse.py
"""Plugin extraction reuses the bundle ingest already paid to fetch."""

from backend.services import plugin_service


def test_plugin_reuses_stored_bundle(monkeypatch):
    """When a repo_bundle artifact exists for the session, GitHub is not re-hit."""
    monkeypatch.setattr(
        plugin_service.supabase_client,
        "fetch_artifact_content",
        lambda session_id, kind, user_id=None: "cached bundle text",
    )

    def explode(*args, **kwargs):
        raise AssertionError("must not re-fetch the repo when a bundle is cached")

    monkeypatch.setattr(plugin_service, "fetch_repo_bundle", explode)

    bundle = plugin_service._load_bundle(
        session_id="sess_1",
        user_id="11111111-1111-1111-1111-111111111111",
        repo_url="https://github.com/octocat/hello",
    )
    assert bundle == "cached bundle text"


def test_plugin_refetches_when_no_bundle_cached(monkeypatch):
    """With no cached bundle, fall back to fetching (a plugin-only run)."""
    monkeypatch.setattr(
        plugin_service.supabase_client,
        "fetch_artifact_content",
        lambda session_id, kind, user_id=None: None,
    )
    monkeypatch.setattr(
        plugin_service, "fetch_repo_bundle", lambda repo_url: "freshly fetched"
    )
    bundle = plugin_service._load_bundle(
        session_id="sess_2",
        user_id="11111111-1111-1111-1111-111111111111",
        repo_url="https://github.com/octocat/hello",
    )
    assert bundle == "freshly fetched"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/backend/test_bundle_reuse.py -v`
Expected: FAIL — `plugin_service` has no `_load_bundle`.

- [ ] **Step 4: Persist the bundle on ingest**

In `backend/services/ingest_service.py`, immediately after the repo bundle is fetched and before the Gemini call, store it:

```python
    # Persist the bundle so /extract-plugin can reuse it instead of paying to
    # fetch and re-send the same 600K tokens to the model a second time.
    supabase_client.insert_artifact(
        session_id=session_id,
        user_id=user_id,
        kind="repo_bundle",
        content=bundle,
        metadata={"repo_url": repo_url},
    )
```

Match the actual `insert_artifact` signature at `paperpilot/supabase_client.py:153` — read it first and adapt the keyword names if they differ.

- [ ] **Step 5: Reuse it on plugin extraction**

In `backend/services/plugin_service.py`, add:

```python
def _load_bundle(session_id: str, user_id: str, repo_url: str) -> str:
    """Return the repo bundle for this session, fetching only if not already stored.

    /ingest already fetched and paid for this bundle. Re-fetching and re-sending
    it doubles the cost of a Productize run for no benefit.
    """
    cached = supabase_client.fetch_artifact_content(
        session_id, "repo_bundle", user_id=user_id
    )
    if cached:
        return cached
    return fetch_repo_bundle(repo_url)
```

Then replace the direct fetch call in the extraction path with `_load_bundle(session_id, user_id, repo_url)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/backend/test_bundle_reuse.py -v && make test`
Expected: 2 passed; full suite green.

- [ ] **Step 7: Write the failing test for the size cap**

Halving the cost is not the same as bounding it. A 600K-token bundle still costs
real money on the user's key, and they should be told before it is spent.

```python
# append to tests/backend/test_bundle_reuse.py
import pytest
from fastapi import HTTPException

from backend.services import ingest_service


def test_large_bundle_requires_confirmation(monkeypatch):
    """A bundle over the threshold is refused until the caller confirms."""
    monkeypatch.setattr(ingest_service, "MAX_UNCONFIRMED_TOKENS", 100)
    with pytest.raises(HTTPException) as exc:
        ingest_service.check_bundle_size(estimated_tokens=5_000, confirm_large=False)
    assert exc.value.status_code == 413
    assert "5,000" in exc.value.detail
    assert "confirm" in exc.value.detail.lower()


def test_large_bundle_proceeds_when_confirmed(monkeypatch):
    monkeypatch.setattr(ingest_service, "MAX_UNCONFIRMED_TOKENS", 100)
    ingest_service.check_bundle_size(estimated_tokens=5_000, confirm_large=True)


def test_small_bundle_needs_no_confirmation(monkeypatch):
    monkeypatch.setattr(ingest_service, "MAX_UNCONFIRMED_TOKENS", 100_000)
    ingest_service.check_bundle_size(estimated_tokens=5_000, confirm_large=False)
```

- [ ] **Step 8: Run it to verify it fails**

Run: `uv run pytest tests/backend/test_bundle_reuse.py -v`
Expected: FAIL — `ingest_service` has no `check_bundle_size`.

- [ ] **Step 9: Implement the cap**

Add to `backend/services/ingest_service.py`:

```python
import os

from fastapi import HTTPException, status

# Above this, the caller is told what the run will cost them and must opt in.
# The bundle can reach 600K tokens (paperpilot/github_ingest.py:26), which is
# real money on the user's own key -- they should spend it deliberately.
MAX_UNCONFIRMED_TOKENS = int(os.environ.get("MAX_UNCONFIRMED_TOKENS", "150000"))


def check_bundle_size(estimated_tokens: int, confirm_large: bool) -> None:
    """Refuse an oversized ingest until the caller has confirmed it."""
    if confirm_large or estimated_tokens <= MAX_UNCONFIRMED_TOKENS:
        return
    raise HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=(
            f"This repository bundles to roughly {estimated_tokens:,} tokens, "
            f"above the {MAX_UNCONFIRMED_TOKENS:,}-token threshold. It runs on "
            "your own API key. Re-send with confirm_large=true to proceed."
        ),
    )
```

Call it in the ingest path immediately after the bundle is fetched and its token
count estimated, and before the Gemini call. Add `confirm_large: bool = False` to
the `IngestRequest` model in `backend/routers/ingest.py`.

- [ ] **Step 10: Surface the confirmation in the UI**

In `web/app/(app)/productize/page.tsx`, catch the 413 and show the returned
`detail` with a "Run anyway" button that re-sends with `confirm_large: true`. Do
not auto-retry — the entire point is that the user decides.

- [ ] **Step 11: Run tests to verify they pass**

Run: `uv run pytest tests/backend/test_bundle_reuse.py -v && make test`
Expected: 5 passed; full suite green.

- [ ] **Step 12: Commit**

```bash
git add backend/services/ingest_service.py backend/services/plugin_service.py backend/routers/ingest.py web/app/\(app\)/productize/page.tsx tests/backend/test_bundle_reuse.py
git commit -m "Reuse the repo bundle between ingest and plugin extraction, and cap it

The same bundle -- up to 600K tokens -- was fetched and sent to Gemini twice per
Productize run. Store it once on ingest and read it back. Above a threshold, tell
the caller what they are about to spend on their own key and make them confirm."
```

---

### Task 10: Enforce Track quotas server-side

Track runs on Merit's key. Without a quota, one user can run it without bound. Enforcement lives in FastAPI because the backend connects to Supabase as service role and bypasses RLS.

**Quota values (from the spec; adjust only with Andre's sign-off):** 3 dossiers per month, 30 criterion narratives per month, 20 assistant questions per day.

**Files:**
- Create: `backend/quotas.py`
- Modify: `backend/routers/evidence.py` (dossier and narrative routes)
- Modify: `backend/routers/assist.py`
- Test: `tests/backend/test_quotas.py` (create)

**Interfaces:**
- Consumes: `paperpilot.supabase_client.user_event_count(user_id, kind_prefix, since, conn=None) -> int` from Task 4.
- Produces: `backend.quotas.enforce(user_id: str, quota: Quota) -> None` raising `HTTPException(429)`; the `Quota` dataclass and the three module-level quota constants `DOSSIER`, `NARRATIVE`, `ASSIST`.

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_quotas.py
"""Quotas are enforced in the backend, not the UI."""

import pytest
from fastapi import HTTPException

from backend import quotas


def test_under_quota_passes(monkeypatch):
    monkeypatch.setattr(quotas, "user_event_count", lambda *a, **k: 2)
    quotas.enforce("user-1", quotas.DOSSIER)  # 2 < 3, no raise


def test_at_quota_raises_429(monkeypatch):
    monkeypatch.setattr(quotas, "user_event_count", lambda *a, **k: 3)
    with pytest.raises(HTTPException) as exc:
        quotas.enforce("user-1", quotas.DOSSIER)
    assert exc.value.status_code == 429
    assert "3 per month" in exc.value.detail


def test_narrative_quota_is_monthly_thirty(monkeypatch):
    assert quotas.NARRATIVE.limit == 30
    assert quotas.NARRATIVE.window_days == 30


def test_assist_quota_is_daily_twenty(monkeypatch):
    assert quotas.ASSIST.limit == 20
    assert quotas.ASSIST.window_days == 1


def test_ledger_failure_fails_open(monkeypatch):
    """If the ledger cannot be read, do not lock the user out of their own data."""

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(quotas, "user_event_count", boom)
    quotas.enforce("user-1", quotas.DOSSIER)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/test_quotas.py -v`
Expected: FAIL — `No module named 'backend.quotas'`.

- [ ] **Step 3: Implement quotas**

```python
# backend/quotas.py
"""Server-side quotas for the surfaces Merit pays for.

Track and the help assistant run on Merit's API key, so they need a bound. The
bound is enforced here and not in the Next.js client, because the backend
connects to Supabase as service role and bypasses RLS -- anything enforced only
in the UI is enforced nowhere.

Quotas fail OPEN: if the ledger cannot be read, a user is not locked out of
their own evidence. The ledger is a cost-control mechanism, not a security
boundary, and the failure mode of over-serving is much cheaper than the failure
mode of a user unable to reach their own petition data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from paperpilot.supabase_client import user_event_count

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Quota:
    """A limit on how many of one kind of paid-for operation a user may run."""

    kind_prefix: str
    limit: int
    window_days: int
    noun: str


DOSSIER = Quota(kind_prefix="evidence_dossier", limit=3, window_days=30, noun="dossier export")
NARRATIVE = Quota(kind_prefix="evidence_draft", limit=30, window_days=30, noun="criterion narrative")
ASSIST = Quota(kind_prefix="assist", limit=20, window_days=1, noun="assistant question")


def enforce(user_id: str, quota: Quota) -> None:
    """Raise 429 when the user is at or over the limit for this quota."""
    since = datetime.now(timezone.utc) - timedelta(days=quota.window_days)
    try:
        used = user_event_count(user_id, quota.kind_prefix, since)
    except Exception:  # noqa: BLE001 -- fail open, see module docstring
        logger.exception("quota check failed for user=%s quota=%s", user_id, quota.noun)
        return

    if used < quota.limit:
        return

    period = "day" if quota.window_days == 1 else "month"
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"You have used all {quota.limit} {quota.noun}s for this {period} "
            f"({quota.limit} per {period}). This surface runs on Merit's API key, "
            "which is why it is capped."
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/backend/test_quotas.py -v`
Expected: 5 passed.

- [ ] **Step 5: Apply the quotas to the routes**

In `backend/routers/evidence.py`, at the top of the dossier route handler and the narrative route handler respectively:

```python
from backend import quotas

# in the dossier route, before any work:
quotas.enforce(user.id, quotas.DOSSIER)

# in the narrative route, before any work:
quotas.enforce(user.id, quotas.NARRATIVE)
```

In `backend/routers/assist.py`, at the top of the assist route handler:

```python
from backend import quotas

quotas.enforce(user.id, quotas.ASSIST)
```

- [ ] **Step 6: Run the full suite**

Run: `make test`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add backend/quotas.py backend/routers/evidence.py backend/routers/assist.py tests/backend/test_quotas.py
git commit -m "Add server-side quotas to the surfaces Merit pays for

Track and the assistant run on Merit's key and had no bound. Enforced in FastAPI
because the backend bypasses RLS as service role, so a UI-side limit is no limit.
Fails open: a ledger outage must not lock a user out of their own evidence."
```

---

### Task 11: Data export and deletion

Merit stores immigration evidence for users who are predominantly not US nationals. Export and deletion are obligations regardless of whether money changes hands. The `on delete cascade` FKs at `supabase/migrations/20260616161439_initial_schema.sql:136-167` say deletion should cascade; this task verifies it rather than assuming it.

**Files:**
- Create: `backend/routers/account.py`
- Modify: `backend/main.py` (register the router)
- Test: `tests/backend/test_account.py` (create)

**Interfaces:**
- Consumes: `backend.auth.CurrentUser`; `paperpilot.supabase_client.get_conn`.
- Produces: `GET /account/export` returning a JSON object with keys `profile`, `evidence`, `outreach_log`, `artifacts`; `DELETE /account` returning 204 and removing the `auth.users` row (which cascades).

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_account.py
"""A user can get their data out and can delete it."""

from fastapi.testclient import TestClient

from backend.auth import AuthUser, get_current_user
from backend.main import app

USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email="ada@example.com")


def _as_user():
    app.dependency_overrides[get_current_user] = lambda: USER


def test_export_requires_auth():
    with TestClient(app) as client:
        resp = client.get("/account/export")
    assert resp.status_code == 401


def test_export_returns_every_table_keyed_to_the_user(monkeypatch):
    from backend.routers import account

    monkeypatch.setattr(
        account,
        "_collect_user_data",
        lambda user_id: {
            "profile": {"name": "Ada"},
            "evidence": [{"criterion": "awards"}],
            "outreach_log": [],
            "artifacts": [],
        },
    )
    _as_user()
    try:
        with TestClient(app) as client:
            resp = client.get("/account/export")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"profile", "evidence", "outreach_log", "artifacts"}
    assert body["evidence"][0]["criterion"] == "awards"


def test_delete_removes_the_auth_user(monkeypatch):
    from backend.routers import account

    deleted = []
    monkeypatch.setattr(account, "_delete_user", lambda user_id: deleted.append(user_id))
    _as_user()
    try:
        with TestClient(app) as client:
            resp = client.delete("/account")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204
    assert deleted == [USER.id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/test_account.py -v`
Expected: FAIL — 404 on both routes; `backend.routers.account` does not exist.

- [ ] **Step 3: Implement the account router**

```python
# backend/routers/account.py
"""Data export and account deletion.

Merit holds immigration evidence, which is sensitive personal data for users who
are predominantly not US nationals. Getting it out and getting it deleted are
obligations that exist whether or not anyone is paying us.

Deletion removes the auth.users row; every per-user table declares
`references auth.users(id) on delete cascade`, so the cascade does the rest. The
test suite verifies the cascade rather than trusting the schema comment.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from backend.auth import AuthUser, CurrentUser
from paperpilot import supabase_client

router = APIRouter(prefix="/account", tags=["account"])


def _collect_user_data(user_id: str) -> dict[str, Any]:
    """Return every row Merit holds for this user, grouped by table."""
    conn = supabase_client.get_conn()
    try:
        def rows(sql: str) -> list[dict[str, Any]]:
            cur = conn.execute(sql, (user_id,))
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        profile = rows("SELECT * FROM user_profile WHERE user_id = %s")
        return {
            "profile": profile[0] if profile else None,
            "evidence": rows("SELECT * FROM o1_evidence WHERE user_id = %s"),
            "outreach_log": rows("SELECT * FROM outreach_log WHERE user_id = %s"),
            "artifacts": rows(
                "SELECT id, session_id, kind, content_hash, metadata, created_at "
                "FROM session_artifacts WHERE user_id = %s"
            ),
        }
    finally:
        conn.close()


def _delete_user(user_id: str) -> None:
    """Delete the auth.users row, cascading to every per-user table."""
    conn = supabase_client.get_conn()
    try:
        conn.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


@router.get("/export")
def export_account(user: AuthUser = CurrentUser) -> dict[str, Any]:
    """Return everything Merit stores about the caller."""
    return _collect_user_data(user.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: AuthUser = CurrentUser) -> Response:
    """Delete the caller's account and all data keyed to it."""
    _delete_user(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

Register it in `backend/main.py` after line 54:

```python
from backend.routers import account
app.include_router(account.router)
```

Note `session_artifacts` content is deliberately excluded from the export payload's artifact rows (it holds base64 zips and full LaTeX, which would make the export enormous); the metadata is exported and the content is retrievable via the existing artifact endpoint.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/backend/test_account.py -v && make test`
Expected: 3 passed; full suite green.

- [ ] **Step 5: Verify the cascade for real, against cloud Supabase**

This is the step that matters. A mocked test proves the route calls the function; only a live run proves the cascade.

```bash
# Create a throwaway confirmed user via the Supabase admin API, insert one row
# into each per-user table for them, delete the auth.users row, then assert every
# table has zero rows for that user_id.
uv run python scripts/verify_cascade_delete.py
```

Write `scripts/verify_cascade_delete.py` to do exactly that and print PASS or FAIL per table. It must exit non-zero if any table retains rows.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/account.py backend/main.py scripts/verify_cascade_delete.py tests/backend/test_account.py
git commit -m "Add data export and account deletion

Merit holds immigration evidence; export and deletion are obligations
independent of revenue. The cascade is verified against the live database rather
than assumed from the schema."
```

---

### Task 12: Prove per-user isolation on the service-role path

RLS is declared on every per-user table (`supabase/migrations/20260616161439_initial_schema.sql:136-167`), but the FastAPI backend connects as **service role**, which bypasses RLS entirely. On that path, app-level scoping is the only thing keeping one user's evidence away from another. That deserves a test, not an assumption.

**Files:**
- Create: `tests/backend/test_user_isolation.py`
- Modify: any service function found to be missing a `user_id` filter

**Interfaces:**
- Consumes: `backend.services.evidence_service`, `backend.services.market_service`.
- Produces: no new interfaces. This task is a proof, plus fixes for whatever it disproves.

- [ ] **Step 1: Enumerate every read path that takes a user_id**

Run: `grep -rn --include='*.py' "WHERE user_id\|where user_id" backend/ paperpilot/ | grep -v __pycache__`

Every SELECT against a per-user table (`user_profile`, `o1_evidence`, `outreach_log`, `session_artifacts`, `trace_log`) must filter on `user_id`. List any that do not.

- [ ] **Step 2: Write the failing test**

```python
# tests/backend/test_user_isolation.py
"""The service-role backend bypasses RLS, so app-level scoping is the only guard."""

import inspect
import re

import pytest

from backend.services import evidence_service, market_service

PER_USER_TABLES = ["o1_evidence", "outreach_log", "user_profile", "session_artifacts"]

MODULES = [evidence_service, market_service]


def _sql_statements(module) -> list[tuple[str, str]]:
    """Return (function_name, sql_string) for every SQL literal in the module."""
    found = []
    src = inspect.getsource(module)
    for match in re.finditer(r'"((?:SELECT|DELETE|UPDATE)[^"]+)"', src, re.IGNORECASE):
        found.append((module.__name__, match.group(1)))
    return found


@pytest.mark.parametrize("module", MODULES)
def test_every_per_user_query_filters_by_user_id(module):
    """No SELECT/UPDATE/DELETE touches a per-user table without scoping to user_id."""
    offenders = []
    for mod_name, sql in _sql_statements(module):
        collapsed = " ".join(sql.split()).lower()
        touches_user_table = any(t in collapsed for t in PER_USER_TABLES)
        if touches_user_table and "user_id" not in collapsed:
            offenders.append(f"{mod_name}: {collapsed[:90]}")
    assert not offenders, "unscoped queries against per-user tables:\n" + "\n".join(offenders)
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/backend/test_user_isolation.py -v`
Expected: it either passes (isolation holds) or names the offending queries. If it names any, fix each by adding `AND user_id = %s` and threading the caller's id through — then re-run until green.

- [ ] **Step 4: Add the live two-user check**

```bash
# Create two throwaway users, give each one evidence row, then assert that
# reading as user A never returns user B's row through the real service layer.
uv run python scripts/verify_two_user_isolation.py
```

Write `scripts/verify_two_user_isolation.py` to do exactly that against cloud Supabase, printing PASS or FAIL and exiting non-zero on any leak.

- [ ] **Step 5: Commit**

```bash
git add tests/backend/test_user_isolation.py scripts/verify_two_user_isolation.py backend/services/
git commit -m "Prove per-user isolation on the service-role path

The backend connects as service role and bypasses RLS, so app-level user_id
scoping is the only thing separating tenants on that path. Assert it statically
and verify it live with two real users."
```

---

### Task 13: Disclaimers on AI-generated petition content

Merit drafts petition narratives against the eight USCIS O-1A criteria. Being free lowers the stakes of a UPL claim; it does not remove them. This is three lines of copy and it is the cheapest risk reduction available.

**Files:**
- Create: `web/components/LegalDisclaimer.tsx`
- Modify: `web/app/(app)/track/page.tsx` (narrative panel and dossier export)
- Modify: `backend/services/evidence_service.py` (dossier PDF footer)
- Test: `web/__tests__/legal-disclaimer.test.tsx` (create, if a test runner exists; otherwise assert via the E2E path)

**Interfaces:**
- Consumes: nothing.
- Produces: `<LegalDisclaimer variant="inline" | "pdf" />` React component.

- [ ] **Step 1: Write the component**

```tsx
// web/components/LegalDisclaimer.tsx
/**
 * Shown wherever Merit produces AI-generated petition content.
 *
 * Merit drafts narratives against the USCIS O-1A criteria. It is a document
 * preparation tool, not a law firm, and it must never read as though it is one.
 */

interface LegalDisclaimerProps {
  className?: string;
}

export const DISCLAIMER_TEXT =
  "This content is generated by AI from the evidence you entered. Merit is a " +
  "document preparation tool, not a law firm, and this is not legal advice. " +
  "No immigration outcome is guaranteed. Have a licensed immigration attorney " +
  "review your petition before you file.";

export function LegalDisclaimer({ className = "" }: LegalDisclaimerProps) {
  return (
    <p
      role="note"
      className={`text-xs leading-relaxed text-neutral-600 ${className}`}
    >
      {DISCLAIMER_TEXT}
    </p>
  );
}
```

- [ ] **Step 2: Place it at every point AI petition content is produced**

In `web/app/(app)/track/page.tsx`, render `<LegalDisclaimer />` directly beneath the criterion-narrative output panel and directly beneath the dossier export button. Not in a collapsed accordion, not in a footer on another page.

- [ ] **Step 3: Add the same text to the PDF**

In `backend/services/evidence_service.py`, in the reportlab dossier builder (around `evidence_service.py:531-612`), append the disclaimer as a final paragraph on the last page:

```python
DISCLAIMER_TEXT = (
    "This content is generated by AI from evidence entered by the applicant. "
    "Merit is a document preparation tool, not a law firm, and this is not legal "
    "advice. No immigration outcome is guaranteed. Have a licensed immigration "
    "attorney review this petition before filing."
)
```

Render it in the dossier's closing section with the existing paragraph style.

- [ ] **Step 4: Verify visually**

Run the app, generate a narrative, and export a dossier. Confirm the disclaimer appears in both the UI and the PDF.

```bash
make api  # in one terminal
cd web && npm run dev  # in another
```

- [ ] **Step 5: Write the privacy policy**

The spec requires one, and it is not boilerplate: Merit stores immigration
evidence for users who are predominantly not US nationals, which puts GDPR in
scope regardless of revenue.

Create `web/app/privacy/page.tsx` as a plain, readable page (no legalese padding)
that states, at minimum:

- **What is stored:** account email; profile (name, title, links, resume text);
  evidence records (title, description, URL, date, criterion); outreach logs;
  generated artifacts (LaTeX, BibTeX, plugin zips); usage traces (model, tokens,
  cost, timestamps).
- **What is not stored:** your API key. It is held in your browser, sent with each
  request, used to make the call, and never written to disk, a log, or a database.
- **Who it is shared with:** the model providers Merit routes to via Vercel AI
  Gateway (Google, Anthropic, OpenAI) receive the content you submit for
  generation. Nobody else. Merit does not sell data and has no advertisers.
- **Retention and deletion:** data persists until you delete your account, at
  which point every row keyed to you is removed (see Task 11).
- **Your rights:** export at any time via the account page; deletion at any time
  via the account page.
- **Self-hosting:** if you run Merit yourself, none of the above involves us at
  all — the data is in your own Supabase project.

Link it from the app footer and from the signup page.

- [ ] **Step 6: Commit**

```bash
git add web/components/LegalDisclaimer.tsx web/app/\(app\)/track/page.tsx web/app/privacy/page.tsx backend/services/evidence_service.py
git commit -m "Disclaim AI-generated petition content and publish a privacy policy

Merit drafts against the USCIS criteria and must never read as a law firm.
Immigration evidence is sensitive personal data whether or not anyone is paying,
so say plainly what is stored, what is not (the user's API key), and who it goes
to."
```

---

### Task 14: Open-source packaging and the public flip

The last task. Everything above must be green first.

**Files:**
- Create: `LICENSE`
- Modify: `README.md`
- Modify: `.env.example`
- Create: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: everything.
- Produces: a repository someone can clone and run with a single gateway key.

- [ ] **Step 1: Add the MIT license**

Create `LICENSE` with the standard MIT text, copyright `2026 Andre Chuabio`.

MIT rather than a copyleft license: the argument for AGPL is protecting a hosted revenue stream, and there is no revenue to protect. MIT maximizes adoption, which is the point of open-sourcing.

- [ ] **Step 2: Document the BYOK setup in .env.example**

Add to `.env.example`, replacing the existing gateway line:

```bash
# Merit calls three providers -- Google (repo ingest), Anthropic (drafting), and
# OpenAI (embeddings) -- so a single provider key cannot run the pipeline. One
# Vercel AI Gateway key routes to all three.
# Get one free at https://vercel.com/dashboard/ai-gateway
AI_GATEWAY_API_KEY=

# OPTIONAL. Everything below is an enhancement, not a requirement. Merit runs
# without any of it.
SENSO_API_KEY=          # optional: brand-kit tone retrieval for outreach drafts
NIMBLE_API_KEY=         # optional: contact discovery for outreach targets
DD_API_KEY=             # optional: Datadog LLM observability
ALLOW_DEV_AUTH=         # set to 1 ONLY for local development of the legacy Streamlit app
```

- [ ] **Step 3: Rewrite the README opening**

The README must answer, in the first screen: what Merit is, what one key you need, and how to run it. State plainly that Senso and Nimble are optional and that nothing breaks without them.

Include an explicit "What this is not" line: Merit is a document preparation tool, not a law firm, and it does not give legal advice.

- [ ] **Step 4: Verify the clean-clone experience**

This is the acceptance test for the whole plan. Do it in a scratch directory, not in the working tree.

```bash
cd $(mktemp -d)
git clone https://github.com/AndreChuabio/MeritAI.git
cd MeritAI
cp .env.example .env
# Put ONLY AI_GATEWAY_API_KEY in .env. No Senso. No Nimble. No Datadog.
uv sync
make test
make api
```

Then, against that instance: generate an outreach draft. It must produce markdown, not an error card. If it does not, Task 7 is incomplete.

- [ ] **Step 5: Final secret sweep before flipping public**

```bash
git log --all --diff-filter=A --name-only -- '*.env*'   # must show only .env.example
grep -rn --include='*' -e 'sk-ant-' -e 'AIza' -e 'vck_' . | grep -v node_modules | grep -v '\.git/'
```

Expected: no credential values anywhere. (A full-history audit on 2026-07-14 found the repo clean and `.gitignore` has excluded `.env` since the initial commit `da540e0`, so this is a confirmation, not a search.)

- [ ] **Step 6: Commit, then flip the repo public**

```bash
git add LICENSE README.md CONTRIBUTING.md .env.example
git commit -m "Add MIT license and open-source setup docs

Merit runs on one Vercel AI Gateway key. Senso, Nimble, and Datadog are optional
enhancements and nothing breaks without them."
```

Flipping the repository to public is a **manual step for Andre**, not an agent action. Do not run `gh repo edit --visibility public`. Report that the repo is ready and let him make the call.

---

## Notes for the implementer

**Task order matters in three places.** Task 4 depends on Task 3 (no ledger, no cost query). Task 10 depends on Task 4 (no cost query, no quota). Task 7 depends on Task 5 (un-vendored drafting runs on the caller's key). Everything else is independent and can be done in any order.

**Tasks 1, 2, and 14 are the open-source critical path.** If Nikki needs the repo public before the rest lands, those three plus a `make test` green run are sufficient — BYOK, quotas, and the ledger can follow. Say so rather than blocking her on the full plan.

**Do not rename the `paperpilot` package.** It is load-bearing across every import in the repo and renaming it buys a user nothing.
