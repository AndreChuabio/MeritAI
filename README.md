# Productionize Your Product

Three agentic surfaces on one stack: turn your GitHub repo into a research paper, draft your personal-brand outreach for it, and track your O-1 / National Interest Waiver visa progress. Every LLM call traced.

Built at the **Agentic Engineering Hack NYC**, 2026-05-23, at Datadog HQ. Live at **https://paperpilot-production-97dc.up.railway.app**.

---

## What it does

A three-page Streamlit app (`Productize.py` entry + `pages/Market.py` + `pages/Track.py`) on a shared agentic spine.

### 📄 Productize — repo → paper draft for a matched venue

1. **Ingest.** Pulls README + file tree + ranked source files from any GitHub repo. Concatenates into a single bundle under a 600K-token cap.
2. **Summarize.** Sends the bundle to Gemini 2.5 Flash through Vercel AI Gateway (1M-context window). Returns a structured `ResearchSummary`: problem, contribution, method, results, limitations, keywords.
3. **Match.** Embeds the summary and ranks 53 CFPs (41 curated + 12 Nimble-discovered) in ClickHouse Cloud by semantic fit + deadline proximity. **Augmented with live Nimble Search:** queries the open web in parallel and merges the top 3 hits into the candidate pool. Venue cards carry a `LIVE · Nimble` or `Curated` badge.
4. **Draft.** Streams the paper section-by-section through Claude Sonnet 4.6. Pre-pended with **Senso KB tone exemplars** retrieved per `(venue, section)`. Related-work citations are gated against an arxiv corpus pre-filter; unsanctioned `[arxiv:...]` markers are stripped post-hoc with a visible warning.
5. **Export.** LaTeX + BibTeX, ready to open in Overleaf. Auto-persisted to ClickHouse `session_artifacts`.
6. **Extract Claude plugin.** A second pass over the same repo bundle identifies reusable units and packages them as a complete Claude Code plugin: `SKILL.md` files, slash commands, subagents, lifecycle hooks, MCP build prompts, all bundled with a `plugin.json` in the standard `~/.claude/plugins/<name>/` layout. Drop-in zip.

### 📣 Market — outreach drafting on a Senso brand kit

- **Personal Brand tab.** Save / load a profile (name, title, voice, links, resume) into a Senso `brand_kit` so all subsequent drafts inherit the user's voice.
- **Generate Content tab.** Pick a purpose (VISA, SPEAKING, COLLAB, NETWORK), describe the goal, get drafts back via Senso's content-generation pipeline. Each draft includes a `cost_source`-tagged trace.
- **Search People tab.** Discover GitHub users / open-source maintainers via the `github_repos.py` helper.
- **Blast tab.** Schedule + dispatch drafts to outbound channels.

### 📈 Track — O-1 + National Interest Waiver progress dashboard

Aggregates every signal we have about the candidate's readiness for an O-1 (extraordinary ability) and NIW case:

- Authored scholarly articles (Google Scholar via `outreach/scholar.py`)
- Citations & impact (Scholar academic + Senso AI)
- Speaking + collaboration outreach drafted vs. posted (from `outreach_log`)
- Headline gauges per USCIS criteria set + per-channel bar chart + drafts-over-time line

### 🟢 Observability throughout

Every LLM call wrapped by `trace.step(...)` → in-process buffer (UI right rail) + ClickHouse `trace_log` (audit) + **Lapdog** local dashboard + **Datadog LLM Observability** cloud forward. Cost+token pill in the right rail sums every `.end` event with a `(est.)` tag when the Gateway omits usage on streamed responses.

---

## Architecture

```
              Streamlit UI (localhost)
                       |
        wrapped by:  lapdog
                       |
        +--------------+---------------+
        |              |               |
   GitHub API   Vercel AI Gateway   ClickHouse Cloud
   (PyGithub)   - Gemini ingest    - cfp(scope_emb)
                - Claude draft     - arxiv(emb)
                - text-embed-3     - trace_log
                       |
                 arxiv API (Python)
                 (citation grounding)
```

| Layer | Stack | Sponsor |
|-------|-------|---------|
| LLM routing | OpenAI-compatible client → multi-provider | **Vercel AI Gateway** |
| Long-context ingest | Gemini 2.5 Flash, 1M-ctx | **DeepMind** |
| Drafting | Claude Sonnet 4.6, streamed | **Anthropic** |
| Vector search + audit + artifacts | ClickHouse Cloud — 4 tables: `cfp`, `arxiv`, `trace_log`, `session_artifacts` | **ClickHouse** |
| Live web data | `/v1/search` + `/v1/search?include_answer` + `/v1/extract` | **Nimble** |
| Brand + tone KB | `/org/brand-kit` + `/org/kb/raw` + `/org/search/context` + `/org/content-generation` | **Senso** |
| LLM observability | Lapdog local + Datadog LLM Observability cloud (`DD_LLMOBS_AGENTLESS_ENABLED=1`) | **Datadog** |
| Cost + token accounting | `tiktoken` fallback + per-model price table, `cost_source: gateway\|estimated` | (observability) |
| Citation grounding | arxiv corpus pre-filter + post-hoc regex strip | (anti-hallucination) |
| Deployment | Railway (Nixpacks builder, Streamlit on `$PORT`) | (infra) |

---

## Observability

Every LLM call in PaperPilot is wrapped by `trace.step(...)` in `paperpilot/trace.py`, which records a `.start` and `.end` event into:

- An **in-process buffer** keyed by `session_id`, drained by the Streamlit right rail.
- **ClickHouse** `trace_log` table (best-effort; never fails the user-facing run).
- **Lapdog** locally + **Datadog LLM Observability** when `DD_LLMOBS_AGENTLESS_ENABLED=1` is set.

Each `.end` event payload carries `tokens_in`, `tokens_out`, `cost_usd`, `dur_ms`, and a `cost_source: "gateway" | "estimated"` discriminator.

### Cost + token capture

We learned mid-build that the Vercel AI Gateway does not reliably propagate `usage` on streamed Anthropic responses — even with `stream_options={"include_usage": True}` set. So `paperpilot/draft.py` implements a graceful fallback:

1. Prefer real `usage.prompt_tokens` / `usage.completion_tokens` / `usage.cost` from the final stream chunk when the Gateway returns it.
2. Fall back to a local `tiktoken` (cl100k_base) count of `sys_prompt + user_prompt` for input tokens, and the accumulated stream for output tokens.
3. Estimate cost from a small per-million-token price table (`_PRICE_PER_MTOK`) keyed by model prefix.
4. Tag every event with `cost_source` so the UI pill can show `(est.)` honestly when estimation was used.

The session pill at the top of the Agent trace panel sums `tokens_in`, `tokens_out`, and `cost_usd` across every `.end` event in the current session — including ingest, citation candidates, venue match, and all four drafted sections. A full nanoGPT-scale run costs roughly **$0.01** end-to-end.

### Session artifact persistence

Every generated artifact (LaTeX paper, BibTeX, Claude Code plugin zip) is written to ClickHouse's `session_artifacts` table, tagged by `session_id`, `repo`, and `venue`. The right-rail "Past sessions" panel pulls the most recent 10 rows on every render so judges can replay any prior run, see the size of each artifact, and re-download from ClickHouse without re-running the pipeline. Plugin zips are stored base64-encoded (the `content` column is `String`); tex/bib are stored as plain UTF-8. Writes are best-effort with structured `artifact.<kind>.save_failed` trace events on failure -- the user-facing download is never blocked by a ClickHouse outage.

### Live web data (Nimble)

`paperpilot/nimble_client.py` wraps three Nimble SDK endpoints (`/v1/search`, `/v1/search` with `include_answer: true`, `/v1/extract`) behind a 5-8s timeout and `trace.step` instrumentation. Three surfaces in the UI use it:

- **Venue discovery (critical path, `cfp_match.py:_nimble_candidate_venues`).** Nimble Search runs alongside the ClickHouse cosine-distance ranking and contributes up to 3 live web venues into the candidate pool. Each hit is embedded and scored with the same formula as curated venues so they compete fairly. UI venue cards carry a `LIVE · Nimble` or `Curated` badge.
- After ingest, the chosen venue card exposes a **Live web check** that runs Search (top hits for `<venue> <year> deadline`) + Extract (the CFP page itself) to validate the curated `data/cfp_seed.json` against live web reality.
- After plugin extraction, **Check prior art** runs Nimble Answers ("are there existing Claude Code plugins / MCP servers that do this?") so the user can see ecosystem overlap before publishing.

Set `NIMBLE_API_KEY` to enable; without it the buttons hide, venue ranking falls back to ClickHouse-only, and the sponsor wire shows `off`. All Nimble calls show up in the trace panel under the orange `nimble.*` color.

---

## Quickstart

```bash
# 0. Prereqs: macOS, uv, brew, gh CLI.

# 1. Install dependencies
uv sync
brew install datadog/lapdog/lapdog

# 2. Configure
cp .env.example .env
# Required: AI_GATEWAY_API_KEY, CLICKHOUSE_HOST/USER/PASSWORD
# Recommended: DD_API_KEY + DD_SITE + DD_LLMOBS_ENABLED=1 + DD_LLMOBS_ML_APP for cloud forward
# Recommended: NIMBLE_API_KEY for live venue discovery + verification + prior-art
# Recommended: SENSO_API_KEY for brand-kit + tone KB + outreach drafting

# 3. Seed corpora
make seed        # CFP + arxiv embeddings into ClickHouse
make seed-senso  # tone exemplars into Senso KB

# 4. Launch
make dev
# -> http://localhost:8501  (Streamlit UI)
# -> http://localhost:8126  (Lapdog local)
# -> https://lapdog.datadoghq.com (Lapdog browser dashboard, reads from :8126)
# -> Datadog LLM Observability cloud (when DD_LLMOBS_AGENTLESS_ENABLED=1)
```

### Production deploy (Railway)

The repo includes `railway.toml` + `nixpacks.toml` + `scripts/railway_env_setup.sh`:

```bash
railway login
railway init --name paperpilot
make railway-env       # pushes every .env var (with --skip-deploys) + auto-sets DD_LLMOBS_AGENTLESS_ENABLED=1
make railway-deploy    # railway up --detach
```

Live URL is printed by `railway domain` (or generated automatically). The production container ships LLM traces to Datadog cloud directly via the agentless ddtrace mode since Lapdog is macOS-only.

### Three pages in the live app

- **Productize** (`Productize.py`). Paste a GitHub URL (or click a chip: nanoGPT, transformers, llama.cpp, PaperPilot). Ingest → match → draft → export `.tex/.bib`. "Extract plugin" runs the Claude Code plugin extractor on the same bundle. "Load demo cache" replays a precomputed `data/demo_cache.json` with a 6-second synthetic event drip (Wi-Fi-failure insurance).
- **Market** (`pages/Market.py`). Personal Brand / Generate Content / Search People / Blast tabs over a Senso brand-kit.
- **Track** (`pages/Track.py`). O-1 + NIW progress gauges + Scholar citation tracking + drafts-vs-posted analytics.

`make ping` runs a CLI hello-world. `make precompute URL=...` refreshes the demo cache. `make meta` runs PaperPilot on its own repo to regenerate `submission/paperpilot.tex`.

---

## Project structure

```
agentichack/
  Productize.py                   Streamlit entry: repo -> paper -> plugin
  pages/
    Market.py                       Senso brand kit + outreach drafting (4 tabs)
    Track.py                        O-1 + NIW progress dashboard

  paperpilot/
    github_ingest.py              PyGithub repo -> ranked file bundle
    llm_ingest.py                 Gemini 1M-ctx -> structured ResearchSummary
    embed.py                      text-embedding-3-small via Gateway
    cfp_match.py                  cosineDistance venue ranking + Nimble live merge
    arxiv_lookup.py               citation candidate pre-filter (ClickHouse + arxiv)
    draft.py                      section streaming + Senso tone + citation strip + tiktoken/cost fallback
    skill_extract.py              repo bundle -> structured PluginPack via Gemini
    skill_render.py               PluginPack -> Claude Code plugin directory zip
    nimble_client.py              Search / Answers / Extract HTTPS client
    senso_client.py               KB ingest + search_context (tone retrieval for Productize)
    clickhouse_client.py          schema + trace_log + session_artifacts
    latex_export.py               .tex + .bib assembly
    pipeline.py                   end-to-end orchestrator + demo cache + save_artifact
    trace.py                      log_event + step context manager + in-process buffer
    gateway.py                    Vercel AI Gateway client
    llm_ping.py                   Phase 1 hello-world helper
    outreach/                     Market + Track logic
      senso.py                      Senso brand-kit + content-types + content-generation
      log.py                        UserProfile + draft log (ClickHouse-backed)
      orchestrator.py               generate_drafts orchestration
      purpose.py                    VISA / SPEAKING / COLLAB / NETWORK enum + prompts
      scholar.py                    Google Scholar fetch for Track dashboard
      content_types.py              Senso content-type seed helpers
      github_repos.py               Find people via GitHub for outreach search

  data/
    cfp_seed.json                 41 hand-curated CFPs
    arxiv_seed.json               223 arxiv papers
    demo_cache.json               precomputed pipeline output for offline demo

  scripts/
    seed_clickhouse.py            embed + insert CFP + arxiv corpora
    seed_senso.py                 ingest tone exemplars into Senso KB
    fetch_arxiv.py                refresh the arxiv corpus
    refresh_cfp_corpus.py         Nimble -> ClickHouse cfp batch refresh (up to 20 venues)
    demo_precompute.py            DEMO_MODE cache writer
    meta_flex.py                  run the agent on this repo itself
    railway_env_setup.sh          push .env into the linked Railway service

  submission/
    paperpilot.tex                meta-flex paper draft (PaperPilot on PaperPilot)
    references.bib                BibTeX for paperpilot.tex
    summary.json                  structured ResearchSummary from meta_flex
    demo_script.md                90s / 60s / 30s pitch + Q&A + fallbacks
    linkedin_post.md              post-hackathon LinkedIn drafts

  railway.toml + nixpacks.toml    Railway deploy config
  Makefile                        dev / seed / ping / precompute / meta / refresh-corpus /
                                  railway-env / railway-deploy / push
```

---

## Citation grounding

Two layers of defense against hallucinated citations in the related-work section:

1. **Candidate pre-filter (ClickHouse).** Embed the repo summary, fetch the top-10 closest arxiv IDs from the corpus by cosine distance. Only those IDs appear in the prompt; the model is instructed to cite ONLY from that list.
2. **Post-hoc strip.** After streaming, regex `\[arxiv:([^\]]+)\]` scans the output; any ID not in the approved set is removed and surfaced in the UI as a "stripped N unapproved citations" warning. Surviving citations are resolved through the in-process `_CACHE` first, falling back to the live arxiv API for BibTeX enrichment.

Result: zero hallucinated citations make it into the final paper. The visible warning when the model attempts an unsanctioned cite is itself a feature — judges can see the gate firing.

---

## The meta-flex

At 16:25 we run PaperPilot on the PaperPilot repo itself:

```bash
make meta
# -> submission/paperpilot.tex
# -> submission/references.bib
# -> submission/summary.json
```

That paper draft ships with the Devpost.

---

## Team

- **Andre Chuabio** ([@AndreChuabio](https://github.com/AndreChuabio)) — engineering: agentic pipeline (Productize), observability, deploy
- **Nikki** — outreach + immigration-track workflow (Market + Track), Senso brand kit, demo-tone review

Built at the **Agentic Engineering Hack NYC** at **Datadog HQ**, 2026-05-23. Sponsors: **Vercel AI Gateway**, **Anthropic**, **DeepMind**, **ClickHouse**, **Nimble**, **Senso**, **Datadog**, **Luminai**.

Live: https://paperpilot-production-97dc.up.railway.app · Code: https://github.com/AndreChuabio/agentichack
