# Merit: BYOK + Open Source Readiness

Date: 2026-07-14
Status: Approved, pending implementation plan

## Context

Merit (formerly PaperPilot) is three agentic surfaces on one stack: Productize
(GitHub repo to research-paper draft), Market (Senso/Nimble outreach), and Track
(O-1A visa evidence ledger and petition dossier). It runs today as a Next.js
frontend on Vercel, a FastAPI backend on Railway, and Supabase Postgres with
pgvector, with a legacy Streamlit app still deployed against ClickHouse.

Two decisions drive this spec:

1. Merit will not charge users for now. Revenue is deferred, not designed out.
2. Users will supply their own LLM API keys, so Merit does not carry token cost
   on its most expensive surface.

A monetization design (Stripe, plans, entitlements, a $49/mo paywall on Track)
was explored and rejected in favour of the above. That work is not carried
forward. No billing code is in scope.

## Goals

- Open-source the Productize surface without leaking credentials or misusing a
  collaborator's identity.
- Let hosted users run Productize on their own API keys, without Merit ever
  taking custody of those keys.
- Keep Track free, hosted, and frictionless, at a cost per user measured in
  cents, with server-side quotas that make abuse bounded rather than unbounded.
- Meet the data-protection and disclosure obligations that apply to a free
  product handling immigration evidence.

## Non-goals

- Payments, subscriptions, plans, entitlements. Explicitly out of scope.
- Organizations, teams, or multi-client tenancy. A user remains exactly one
  `auth.users` row.
- Market. Cut from this scope entirely (see Decisions).

## Product shape

**Merit OSS** is a public repository under MIT. It contains the CFP corpus
schema and a seed corpus, the repo-to-venue matcher, and the drafting pipeline.
Self-hosters configure their own provider keys via `.env`, so this deployment
mode involves no key custody by Merit.

**Merit Hosted** is the existing Vercel + Railway + Supabase deployment.
Productize runs on the user's key (BYOK). Track runs on Merit's keys, free, and
quota-capped.

The funnel connecting them is mechanical, not aspirational: a user who drafts a
paper with Merit and lands it at a venue has produced evidence for the
"scholarly articles" and "original contribution" criteria of an O-1A petition.
The open tool helps build the record; the hosted tool helps assemble the case.

MIT rather than a copyleft license: the moat argument for AGPL only holds if
there is revenue to protect, and there is none. MIT maximizes adoption, which is
the actual goal of open-sourcing.

## Decisions

### BYOK: no server-side key storage

Merit does not persist user API keys. The key is held in the browser, sent with
each request over TLS, used transiently to make the provider call, and
discarded. It is never written to a table, never returned in a response body,
and never logged.

This is chosen over encrypted-at-rest storage because custody Merit does not
have is custody Merit cannot lose. The cost is that a user re-supplies the key
per browser and per device, and that background/offline jobs are impossible for
BYOK surfaces. Both are acceptable: Productize is an interactive, foreground
workflow.

The binding requirement is that the key must not reach any log or trace sink.
Three places can capture it today and each must be scrubbed and tested:

- The FastAPI request path, which runs under `ddtrace-run` for Datadog LLM
  Observability.
- Railway platform request logs.
- `trace_log.payload`, a free-form `jsonb` column.

A test must assert that a request carrying a key produces no log, trace, or row
containing it. A comment claiming this is insufficient.

### Track stays free and hosted, on Merit's keys

Track's cost is roughly $0.05 to $0.10 per dossier and $0.013 per narrative.
The O-1A applicant is frequently non-technical and will not paste an API key;
imposing BYOK there would cost the audience to save cents.

Quotas are enforced server-side in FastAPI. They are not enforced in the Next.js
client, because the backend connects to Supabase as service role and therefore
bypasses RLS; anything enforced only in the UI is enforced nowhere.

Initial limits, generous enough to be invisible to a real user and tight enough
to bound abuse:

- 3 dossier generations per month
- 30 criterion narratives per month
- 20 assistant questions per day

### The usage ledger is the prerequisite

`trace.step` already computes `tokens_in`, `tokens_out`, `cost_usd`, and
`cost_source` on every LLM call, and then discards them: `trace.py:22` imports
`insert_trace` from the ClickHouse client, and `trace.py:79` silently no-ops
when `CLICKHOUSE_HOST` is unset. In the Supabase-era production path the
Supabase `trace_log` table receives exactly one row per session, from
`backend/services/ingest_service.py:61`, carrying no cost fields.

The instrumentation exists; the ledger does not. Repointing `trace.step` at
Supabase with the cost fields intact yields quota enforcement, cost visibility,
and abuse detection from a single change. Every quota above depends on it, so it
lands first.

### Cost tail controls

Even on a user's key, waste is a defect. Today the repo bundle is capped at 600K
tokens (`paperpilot/github_ingest.py:26,29,188`) and is sent to Gemini twice:
once in `/ingest` and again in `/extract-plugin`
(`paperpilot/skill_extract.py:205`). Nothing caps the number of runs.

The bundle must be reused between the two calls rather than re-sent, and the
user must see the bundle size and confirm before a large ingest proceeds.

### Market is cut

`generate_outreach` makes no LLM call of its own; it delegates entirely to Senso
(`paperpilot/outreach/orchestrator.py:86-91`), returning an error card when
unkeyed (`backend/services/market_service.py:283-294`). The people-finder
delegates entirely to Nimble (`market_service.py:209-227`). "Send" opens the
user's mail client; Merit sends nothing. Its vendor COGS is not measurable from
the code.

Market is removed from the v1 story. It is not deleted from the codebase, but it
is not open-sourced, not promoted, and not maintained in this scope.

## Pre-open-source blockers

A full-history audit (all 347 blobs across every ref, plus dangling objects)
found no committed credentials: no provider keys, no Supabase JWTs, no ClickHouse
password, and no `.env` ever committed. `.gitignore` has excluded `.env` since
the initial commit `da540e0`. No history rewrite and no credential rotation are
required.

Two items block flipping the repository public:

1. `paperpilot/auth.py:44` hardcodes `_DEV_USER = {"user_id": "dev", "name":
   "Dev", "passcode": "dev"}` as a fallback when `PAPERPILOT_USERS_JSON` is
   unset. This is not a leaked secret today, but once the repo is public the
   fallback passcode is public. A deployed instance that loses that env var
   becomes world-accessible with a known password. The fallback must fail closed
   — refuse to authenticate — or require an explicit `ALLOW_DEV_AUTH=1`.

2. `data/scholar_seed.json:2` contains `"name": "Nikki Hu"` attached to
   fabricated citation data: invented paper titles and a `?user=DEMO` scholar
   URL. Publishing this presents a real person as the author of papers that do
   not exist. Either she consents or the name is replaced with a fictional one.

The three Railway hostnames in history will become public. They are endpoints,
not secrets, but auth and CORS must be enforced server-side on the assumption
that the URL is known.

## Compliance

Not charging reduces exposure. It does not eliminate it.

**Data protection.** Merit stores immigration evidence for users who are
predominantly not US nationals, which is sensitive personal data with GDPR in
scope regardless of whether money changes hands. Required: a privacy policy
stating what is stored and why; user-initiated data export; user-initiated
deletion that is verified to cascade in practice rather than assumed to from the
`on delete cascade` FK; and an RLS audit that demonstrates per-user isolation
holds, including on the service-role backend path where RLS is bypassed and
app-level scoping is the only control.

**Unauthorized practice of law.** Merit drafts petition narratives against the
eight USCIS O-1A criteria. Being free lowers the stakes of a UPL claim; it does
not immunize against one, and immigration is an area where non-attorney
assistance is actively policed. Required in-product: content is
AI-generated; Merit is a document-preparation tool and not legal advice; no
outcome is guaranteed; consult a licensed immigration attorney. Positioning must
avoid any implication that Merit performs a lawyer's function.

**Counsel review gates launch.** A licensed immigration attorney reviews the
product positioning and the terms of service before Track is publicly available.
This is a blocking dependency, not a follow-up.

## Success criteria

- The repository is public and contains no credential, in HEAD or in history.
- A hosted user completes a Productize run on their own key, and that key appears
  in no log, trace, or database row — demonstrated by a passing test, not by
  inspection.
- A Track user exceeding a quota is refused by the backend, not by the UI.
- Per-user `cost_usd` is queryable from Supabase.
- A user can export their data and delete their account, and deletion is
  observed to remove every row keyed to them.
- Disclaimers are present at each point where AI-generated petition content is
  produced, and counsel has signed off on positioning and terms.
