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
- Let hosted users run the LLM-heavy surfaces on their own API keys, without
  Merit ever taking custody of those keys.
- Ensure every surface works for someone who clones the repo with an LLM key and
  nothing else — no proprietary vendor account required to get a result.
- Keep Track free, hosted, and frictionless, at a cost per user measured in
  cents, with server-side quotas that make abuse bounded rather than unbounded.
- Meet the data-protection and disclosure obligations that apply to a free
  product handling immigration evidence.

## Non-goals

- Payments, subscriptions, plans, entitlements. Explicitly out of scope.
- Organizations, teams, or multi-client tenancy. A user remains exactly one
  `auth.users` row.

## Product shape

Merit is one open-source project, MIT licensed, built on a single primitive.

**The evidence ledger is the primitive.** `o1_evidence` is a structured,
timestamped, URL-backed record of what a person has actually done. Everything
else in Merit either writes to that ledger or renders it.

**One generator.** Productize turns a GitHub repo into a paper draft and matches
it to a venue. A paper landed at a venue is a new row in the ledger. This is the
surface that manufactures evidence.

**Three renderers over the same rows.**

- *Living resume*: the ledger rendered for humans. Evidence-backed proof of work
  — repos, papers, hackathon builds — as an alternative to a credential-based
  CV. This is the general case.
- *O-1A view*: the same ledger rendered against the eight USCIS criteria, with
  drafted narratives and a reportlab PDF dossier. This is a specific export
  format, not a separate product.
- *Outreach (Market)*: the ledger and profile rendered as a purpose-driven
  message to a specific person — visa, speaking, collaboration, network.

The renderers are views, not applications. Each reuses the ledger rather than
duplicating it.

**Deployment modes.** Self-hosters run the whole thing with their own provider
keys in `.env`, so Merit takes no key custody. Merit Hosted (Vercel + Railway +
Supabase) runs Productize on the user's key (BYOK) and the ledger surfaces on
Merit's keys, free and quota-capped, because ledger operations cost cents and
the audience for them is frequently non-technical.

MIT rather than a copyleft license: the moat argument for AGPL only holds if
there is revenue to protect, and there is none. MIT maximizes adoption, which is
the actual goal of open-sourcing.

## Scope of this spec

This spec covers **readiness**: what must be true before Merit can be public and
run on other people's keys. It does not cover building the living-resume
renderer.

That split is deliberate. Readiness is well-understood, small, and unblocks the
open-source release that is the immediate goal. The living resume is a net-new
product surface — the ledger exists, but nothing renders it publicly — and it
deserves its own design pass rather than being smuggled into an infrastructure
plan. Bundling them would trap the fast work behind the slow work.

In scope here:

- Open-source blockers (dev-auth fallback, collaborator name in seed data)
- BYOK with no server-side key custody, and the log-scrubbing that requires
- Un-vendoring Market so it works without a Senso or Nimble account
- The usage ledger fix, and the quotas that depend on it
- Cost-tail controls on repo ingest
- Data protection: export, deletion, RLS audit, disclaimers

Deferred to a follow-up spec:

- The living-resume renderer (public profile, evidence presentation, sharing)

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

### Market stays, and is un-vendored

Market is the third renderer over the ledger and it ships. But it cannot ship in
its current form, because it does not work for anyone who is not us.

`generate_outreach` makes no LLM call of its own; it delegates the entire
generation to Senso (`paperpilot/outreach/orchestrator.py:86-91`) and returns an
error card when no `SENSO_API_KEY` is set
(`backend/services/market_service.py:283-294`). The people-finder delegates
entirely to Nimble (`market_service.py:209-227`) and reports `configured: false`
when unset. Senso and Nimble are niche vendors; substantially none of the
open-source audience holds accounts with either. Publishing this as-is means
publishing a surface that is broken on first run for nearly everyone who clones
it.

The fix is to remove the hard vendor dependency, not to remove the feature:

- **Generation moves to a direct LLM call** on the user's BYOK key — the same
  key already used by Productize. Outreach drafting is text generation
  conditioned on a voice, a purpose, and the user's evidence; it does not need a
  content-platform vendor. Senso remains supported as an optional enhancement
  when a key is present.
- **People-search degrades gracefully.** Without a Nimble key the user supplies
  the recipient themselves, which is the common case regardless. Nimble becomes
  an optional accelerant, not a precondition.
- **Sending is unchanged and honest.** Merit composes; the user's own mail client
  sends. Merit does not send mail on anyone's behalf and does not claim to.

The result is a surface that works out of the box with nothing but an LLM key,
and that gets better if you happen to have the vendor accounts. It also removes
the last place where Merit's cost is not measurable from its own code.

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
eight USCIS O-1A criteria. Required in-product wherever that content is
produced: it is AI-generated; Merit is a document-preparation tool and not legal
advice; no outcome is guaranteed; consult a licensed immigration attorney.
Positioning must avoid any implication that Merit performs a lawyer's function.

**Counsel review: deferred, with an explicit trigger.** No attorney review is
required for this scope. The open-source release carries no UPL exposure — a
self-hosted tool a user runs on their own key is not Merit practicing law — and
hosted Track is currently used only by its author and two known users.

That changes the moment hosted Track is opened to the general public, free or
paid. Being free does not immunize against a UPL claim, and immigration is among
the most actively policed areas for non-attorney assistance. Opening hosted
Track to the public is the trigger to obtain counsel review of positioning and
terms; it is recorded here so the decision is deliberate rather than forgotten.

## Success criteria

- The repository is public and contains no credential, in HEAD or in history.
- A hosted user completes a Productize run on their own key, and that key appears
  in no log, trace, or database row — demonstrated by a passing test, not by
  inspection.
- Someone who clones the repo with only an LLM key configured — no Senso account,
  no Nimble account — can generate an outreach draft. No surface returns an error
  card for a missing vendor key.
- A Track user exceeding a quota is refused by the backend, not by the UI.
- Per-user `cost_usd` is queryable from Supabase.
- A user can export their data and delete their account, and deletion is
  observed to remove every row keyed to them.
- Disclaimers are present at each point where AI-generated petition content is
  produced.
