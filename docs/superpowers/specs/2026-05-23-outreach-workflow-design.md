# Outreach Workflow — Design

**Date:** 2026-05-23
**Author:** Nikki (clinical-ML / Arya Health) + Claude
**Status:** Approved for implementation
**Demo target:** 2026-05-23 17:30 ET (Agentic Engineering Hack NYC, Datadog HQ)

---

## 1. Purpose

Extend PaperPilot beyond the paper-draft moment. Once a user has a paper
summary in ClickHouse, the Outreach workflow helps them **promote, network,
and build the dossier** that converts research output into career outcomes —
including, explicitly, **O-1 / extraordinary-ability visa qualification**.

The workflow is a **front-end onto a Senso workspace** (`Agentic-hack`).
Senso provides the brand framework; we orchestrate purpose-driven content
generation, log everything, and surface a visa-progress dashboard.

## 2. Background

- PaperPilot already produces a structured `ResearchSummary` from any GitHub
  repo and stores it in ClickHouse alongside the trace log.
- Senso (sponsor) offers a brand-management product at `apiv2.senso.ai`
  with: Brand Kit, Knowledge Base, Content Types, Product Lines, async
  content generation, and Citation Trends (GEO — how often AI engines cite
  the user).
- The user's domain context: clinical-ML, healthcare data, real personal
  motivation for the O-1 / visa narrative. The "≥20 academic citations =
  green card secured" heuristic is the dashboard headline.
- Demo time pressure: code freeze 17:00, demo 17:30.

## 3. Non-goals

- Real "Post" actions to LinkedIn / X / email — buttons are no-ops with a
  toast for the demo.
- PDF resume parsing — textarea paste only (PDF upload is a stretch).
- Live Google Scholar scrape — mocked from `data/scholar_seed.json` for the
  demo (Nimble-backed scrape is a stretch).
- Topic Trends / My Prompts / Leaderboard / Model Trends from Senso — out
  of scope today.
- Multi-user support — the workspace has one effective user for the demo.

## 4. Architecture

```
                ┌──────────────────────────────────────┐
                │       Streamlit app.py (+3 tabs)     │
                │                                       │
                │  [Brand] [Outreach] [Track]          │
                └──────────┬───────────────────────────┘
                           │
                           ▼
              paperpilot/outreach/orchestrator.py
                           │
       ┌───────────────────┼───────────────────────┐
       │                   │                       │
       ▼                   ▼                       ▼
  senso.py            scholar.py               log.py
  (Senso client)   (academic cites,      (ClickHouse audit:
                    mock-first)            outreach_log,
                                           user_profile)
       │
       ▼
  apiv2.senso.ai/api/v1
   - PUT  /org/brand-kit
   - GET  /org/brand-kit
   - GET/POST /org/content-types
   - POST /org/knowledge-base/ingest
   - POST /org/product-lines
   - POST /org/content-generation/sample
   - GET  /org/content-generation/sample-jobs/{id}
   - GET  /org/citation-trends/{owned|external}
   - GET  /org/drafts
```

Every Senso call is wrapped in `paperpilot.trace.step()` so the existing
Lapdog → Datadog Cloud pipeline captures it without changes.

## 5. Tab 1: Brand Setup

### UI
- Header: "Your Brand on Senso"
- Form fields:
  - `name` (text)
  - `title` (text, e.g. "ML Engineer, Arya Health")
  - `about` (textarea, ~3-5 sentences)
  - `voice_and_tone` (textarea, free-form per Senso convention)
  - `github_url`, `linkedin_url`, `scholar_url`, `site_url` (text)
  - `resume_text` (textarea — paste resume contents)
- Buttons:
  - **Sync to Senso** → builds payload → `PUT /org/brand-kit`, then writes
    mirror row to ClickHouse `user_profile`.
  - **Load current** → `GET /org/brand-kit`, pre-fills the form.

### Senso payload shape (assembled by `senso.py`)
```json
{
  "brand_name": "<name>",
  "brand_description": "<about>\n\n<resume_text>",
  "voice_and_tone": "<voice_and_tone>",
  "guidelines": {
    "links": {
      "github": "...",
      "linkedin": "...",
      "scholar": "...",
      "site": "..."
    },
    "title": "<title>"
  }
}
```

### ClickHouse mirror
Table `user_profile`:
```
user_id        String      (always "demo" for hackathon)
name           String
title          String
about          String
voice_tone     String
github_url     String
linkedin_url   String
scholar_url    String
site_url       String
resume_text    String
updated_at     DateTime64(3)
```
Purpose of mirror: resilience if Senso is unreachable mid-demo + audit.

## 6. Tab 2: Outreach (Generate)

### UI flow
1. Purpose picker (radio):
   - `VISA` — extraordinary-ability / O-1 dossier-building
   - `CAREER` — networking, job search, mentorship
   - `BRAND` — personal brand building, thought leadership
   - `SERVICE` — selling a service or product
2. "What's this about?" — free-text context (e.g. "I want to apply to keynote at ML4H 2026")
3. Product Line dropdown — list pulled from Senso `/org/product-lines`
   (seeded with PaperPilot summaries). Defaults to most recent.
4. **Generate** button → calls `orchestrator.generate_drafts(...)` which
   for each channel in `PURPOSE_CHANNELS[purpose]`:
   - resolve `content_type_id` (created at seed time, looked up by name)
   - POST `/org/content-generation/sample` with body:
     ```json
     {
       "content_type_id": "<id>",
       "context": "<purpose summary> + <user context> + <product line>"
     }
     ```
     (NOTE: exact field name TBD — Senso docs reference `geo_question_id`;
     during impl, confirm whether we create a geo_question first or pass
     `context` inline. Wrap in `senso.generate(...)` so the caller doesn't
     care which.)
   - poll `GET /org/content-generation/sample-jobs/{id}` (1s interval,
     30s timeout)
   - render `raw_markdown` as a draft card
5. Each draft card has:
   - editable `st.text_area`
   - **Copy** button (uses `st_copy_to_clipboard`)
   - **Post** button — no-op, shows toast "Posted to <channel>" + writes
     `posted=True` row to `outreach_log`

### Purpose → channel mapping (`paperpilot/outreach/purpose.py`)
```python
PURPOSE_CHANNELS = {
    "VISA":    ["email_speaker_pitch", "email_collaboration"],
    "CAREER":  ["linkedin_dm_career"],
    "BRAND":   ["linkedin_post_brand", "x_thread_brand"],
    "SERVICE": ["linkedin_post_brand", "email_service", "x_thread_brand"],
}
```

### Content types seeded by `scripts/seed_senso.py`
| Name | Template (1-line summary) | Writing rules |
|---|---|---|
| `linkedin_post_brand` | 200-300 words, hook + insight + question, first-person | Under 1300 chars; no emojis |
| `linkedin_dm_career`  | Short (<600 chars), warm-intro tone, ends with explicit ask | Use addressee's first name token `{recipient}` |
| `x_thread_brand`      | 4-6 tweet thread | Each tweet ≤280 chars; numbered (1/) |
| `email_speaker_pitch` | Formal pitch to conference organizers | Subject line on first line; signed by `{name}` |
| `email_collaboration` | Academic-warm, references shared topic | Reply-friendly; 150-250 words |
| `email_service`       | Value-first, clear CTA | 150-200 words; one CTA only |

Seeding is **idempotent**: script does `GET /org/content-types`, only
POSTs entries that don't exist.

### Tracing
```python
# trace.step signature in this repo: step(session_id, kind, **payload) -> Iterator[dict]
with trace.step(sid, "senso.generate", purpose=purpose, channel=channel) as ctx:
    job_id = senso.generate_sample(content_type_id, context)
    ctx["job_id"] = job_id
    md = senso.poll_until_done(job_id, timeout_s=30)
    ctx["draft_chars"] = len(md)
```

## 7. Tab 3: Track (Visa Progress)

Four panels, top-to-bottom:

### Panel A — Headline
A single hero card: **"Extraordinary Ability score: 47 / 100"** with a
composite gauge. Formula (pure UX flavor, not a real metric):
```
score = 0.4 * min(scholar_citations / 20, 1.0)
      + 0.3 * min(senso_total_citations / 100, 1.0)
      + 0.3 * min(posted_drafts / 25, 1.0)
score *= 100

# posted_drafts = COUNT(*) FROM outreach_log WHERE posted = 1 AND user_id = 'demo'
```

### Panel B — Academic Citations (Google Scholar)
- Source: `data/scholar_seed.json` for demo
- Shape:
  ```json
  {
    "total": 14,
    "h_index": 5,
    "by_month": [
      {"date": "2025-01", "count": 2}, ...
    ]
  }
  ```
- UI: big number `14 / 20` + progress bar + line chart of `by_month`
- Caption: "≥20 citations is widely cited as the O-1 threshold."
- Stretch: live fetch via Nimble (`scholar.fetch_live(scholar_url)`)

### Panel C — AI Citations (Senso)
- Source: `senso.citation_trends("owned")` + `senso.citation_trends("external")`
- UI: two small tiles side-by-side, each with count + 7-day sparkline
- Caption: "How often ChatGPT, Perplexity, and Claude cite your work."

### Panel D — Recent Drafts
- Source: `senso.list_drafts()` from Senso `Drafts` (Verify & Publish)
- UI: small table — channel | preview (first 80 chars) | status | created_at
- Also pulls from local `outreach_log` for items posted in this session
  but not yet synced to Senso

## 8. ClickHouse additions

In addition to `user_profile` (section 5), add:

```sql
CREATE TABLE outreach_log (
  ts              DateTime64(3) DEFAULT now64(3),
  user_id         String,
  purpose         String,        -- VISA | CAREER | BRAND | SERVICE
  channel         String,        -- linkedin_post_brand | ...
  content_type_id String,
  sample_job_id   String,
  draft_id        String,        -- Senso content_id when available
  posted          UInt8           -- 0 | 1
) ENGINE = MergeTree
ORDER BY (ts, user_id);
```

`paperpilot/outreach/log.py` exposes:
- `log_generate(purpose, channel, job_id) -> row_id`
- `mark_posted(row_id)`

## 9. File layout

```
paperpilot/
  outreach/
    __init__.py
    senso.py          # client (sections 5-7 endpoints)
    purpose.py        # PURPOSE_CHANNELS
    orchestrator.py   # generate_drafts(profile, purpose, context, product_line)
    scholar.py        # mock + Nimble stretch
    log.py            # ClickHouse audit
app.py                # add tabs: Brand, Outreach, Track
scripts/
  seed_senso.py       # idempotent seed of content types + product line + KB
data/
  scholar_seed.json
.env.example          # +SENSO_API_KEY ; +NIMBLE_API_KEY (stretch)
```

## 10. Senso client contract (`paperpilot/outreach/senso.py`)

```python
class Senso:
    def __init__(self, api_key: str, base: str = "https://apiv2.senso.ai/api/v1"): ...

    # Brand Kit
    def get_brand_kit(self) -> dict: ...
    def put_brand_kit(self, payload: dict) -> dict: ...

    # Content Types
    def list_content_types(self) -> list[dict]: ...
    def create_content_type(self, name: str, config: dict) -> dict: ...
    def get_or_create_content_type(self, name: str, config: dict) -> str:
        """Return content_type_id. Idempotent."""

    # Knowledge Base
    def kb_ingest(self, title: str, body: str, source_url: str | None = None) -> dict: ...

    # Product Lines
    def list_product_lines(self) -> list[dict]: ...
    def create_product_line(self, name: str, description: str) -> dict: ...

    # Generation
    def generate_sample(self, content_type_id: str, context: str) -> str:
        """Returns sample_job_id."""
    def get_sample_job(self, job_id: str) -> dict: ...
    def poll_until_done(self, job_id: str, timeout_s: float = 30.0,
                        interval_s: float = 1.0) -> dict: ...

    # Tracking
    def citation_trends(self, scope: Literal["owned", "external"]) -> dict: ...
    def list_drafts(self, limit: int = 10) -> list[dict]: ...
```

All methods raise `SensoAPIError(status, body)` on non-2xx.
Auth header: `X-API-Key: <SENSO_API_KEY>` (per docs).

## 11. Error handling

- **Senso down or 5xx**: catch in orchestrator, surface red toast
  "Senso unavailable — retry?". Tab 1 still saves to `user_profile`.
- **Generation timeout (>30s)**: cancel polling, show partial state
  ("Still cooking — refresh to check") and keep the job_id in the log.
- **Unknown content_type name**: `get_or_create_content_type` creates on
  the fly with a sane default config; logs a warning.
- **Scholar mock missing**: panel B shows "Connect your Scholar profile"
  CTA instead of crashing.

## 12. Observability

Existing pattern preserved. Each Senso request:
```python
with trace.step(sid, "senso.<verb>", **kwargs) as ctx:
    resp = self._http.request(...)
    ctx["status_code"] = resp.status_code
    ctx["duration_ms"] = duration_ms
```
Lapdog captures locally; `DD_API_KEY` forwards to Datadog Cloud as today.

## 13. Demo script (rehearsal-ready)

1. Open Outreach tab → **Brand**. Show Nikki's brand kit pre-filled
   (synced offline before demo). Highlight: voice, scholar link.
2. Switch to **Outreach**. Pick `VISA`. Type:
   "I want to apply to keynote at ML4H 2026."
   Click Generate.
3. Two cards stream in: speaker-pitch email + collaboration email.
   Read aloud the first 2 sentences of the email pitch — judge sees
   real Senso output with academic-warm voice.
4. Switch to **Track**. Headline: "Extraordinary Ability score: 47 / 100".
   Citation panel climbing toward 20. AI citations sparkline. Drafts list
   shows the email we just generated.
5. Pitch close (10 seconds): "From repo → paper → outreach → visa
   dossier, every step traced in Datadog, every draft grounded in Senso."

## 14. Scope-cut order (if time runs out)

1. Composite score formula (Panel A) — fall back to just the 3 tiles
2. PDF resume upload — textarea only is fine
3. Senso Citation Trends tile (Panel C)
4. Product Line dropdown in Tab 2 — use last PaperPilot summary
5. **Never cut:** Tab 2 happy path → pick purpose → drafts appear

## 15. Open questions resolved during brainstorming

- Senso = sponsor; grab API key at their table. ✅
- Profile source: reuse PaperPilot `ResearchSummary` + manual achievements
  textarea. ✅
- Citation source: Scholar (academic) + Senso (AI) side-by-side. ✅
- Demo cut: all three tabs, minimal each. ✅
- "Post" buttons are no-op toasts for demo. ✅

## 16. Risks

| Risk | Mitigation |
|---|---|
| Senso API shape differs from docs (e.g. `geo_question_id` flow) | `senso.generate_sample` abstracts the shape; impl confirms at first call |
| Senso slow (>30s per draft) | Per-channel timeout; stream cards as they arrive |
| Nimble Scholar scrape blocked | Mock from `scholar_seed.json` is the demo path |
| API key not received by demo time | Seed script + UI work read-only against cached fixtures |
