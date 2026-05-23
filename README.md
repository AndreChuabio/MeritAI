# PaperPilot

Drop a GitHub repo. Get a research paper draft for a matched Call-for-Papers. Every LLM call traced.

Built at the **Agentic Engineering Hack NYC**, 2026-05-23, at Datadog HQ.

---

## What it does

PaperPilot turns a GitHub repository into a venue-targeted academic paper draft:

1. **Ingest.** Pulls the README, file tree, and a ranked sample of source files from any GitHub repo. Concatenates into a single bundle under a 600K-token cap.
2. **Summarize.** Sends the bundle to Gemini through Vercel AI Gateway (1M-context window). Gets back a structured `ResearchSummary`: problem, contribution, method, results, limitations, keywords.
3. **Match.** Embeds the summary and ranks 41 hand-curated CFPs (NeurIPS, ICLR, ICML, ACL, EMNLP, KDD, CVPR, ML4H, MICCAI, CHIL, AMIA, workshops, journals) in ClickHouse Cloud by semantic fit + deadline proximity. **Augmented with live Nimble Search:** the same step also queries the open web for "<keywords> conference <year> paper submission deadline," embeds each web hit against the summary, and merges the top 3 into the candidate pool. Venue cards in the UI carry a `LIVE · Nimble` or `Curated` badge so the source is always visible.
4. **Draft.** Streams a paper section-by-section through Claude: abstract, intro, related work, method. The related-work section is citation-grounded — the model is given a pre-filtered list of arxiv candidates from ClickHouse and a strict "cite ONLY these" instruction. Any unsanctioned `[arxiv:...]` marker is stripped post-hoc with a visible warning.
5. **Export.** Downloads as LaTeX + BibTeX, ready to open in Overleaf.
6. **Extract Claude plugin (bonus).** A second pass over the same repo bundle identifies reusable units inside the code and packages them as a complete Claude Code plugin: `SKILL.md` files, slash commands, subagents, lifecycle hooks (PreToolUse / PostToolUse / Stop / etc.), and MCP server build prompts -- bundled with a `plugin.json` manifest in the standard `~/.claude/plugins/<name>/` layout. Download as a single drop-in zip.

Every LLM call is captured by **Lapdog** (Datadog's local LLM-observability CLI) and forwarded to Datadog cloud with one env var. The UI also surfaces a live **cost + token pill** on every run: $X.XXXX spent, N tokens in / out, summed across Gemini ingest and all four Claude draft sections.

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
| LLM telemetry | Lapdog local + Datadog cloud forward | Datadog |
| Long-context ingest | Gemini 2.5 Flash via AI Gateway | DeepMind |
| Drafting | Claude Sonnet 4.6 streamed via AI Gateway | Vercel AI Gateway |
| Vector search + audit log + session artifacts | ClickHouse Cloud (`cfp`, `arxiv`, `trace_log`, `session_artifacts`) | ClickHouse |
| Live web data | Nimble Search + Answers + Extract (`paperpilot/nimble_client.py`) | Nimble |
| Cost + token accounting | `tiktoken` fallback + per-model price table | (observability) |
| Citation grounding | arxiv API + ClickHouse pre-filter + post-hoc strip | (anti-hallucination) |
| Demo venue | ML4H 2026 | (clinical-ML authenticity) |

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
# 0. Prereqs: macOS, uv, brew, gh CLI. (Vercel AI Gateway is HTTPS-only -- no CLI needed.)

# 1. Install dependencies
uv sync
brew install datadog/lapdog/lapdog

# 2. Configure
cp .env.example .env
# Required: AI_GATEWAY_API_KEY, CLICKHOUSE_HOST/USER/PASSWORD
# Optional: DD_API_KEY, DD_SITE, DD_LLMOBS_ENABLED=1, DD_LLMOBS_ML_APP for cloud forward
# Optional: NIMBLE_API_KEY to enable live Search/Answers/Extract on venue cards + plugin extractor

# 3. Seed corpora into ClickHouse (CFPs + arxiv embeddings)
make seed

# 4. Launch
make dev
# -> http://localhost:8501  (Streamlit UI)
# -> http://localhost:8126  (Lapdog dashboard)
# -> Datadog LLM Observability (cloud) via DD_LLMOBS_AGENTLESS_ENABLED=1 forward
```

### Demo flows on the Streamlit UI

- **Pipeline tab.** Paste a GitHub URL (or click a chip: nanoGPT, transformers, llama.cpp, PaperPilot). "Ingest + match venues" runs the full Gemini summary + ClickHouse venue ranking. Pick a venue → live streamed Claude draft with the cost pill climbing in the right rail. After ingest, "Extract plugin" runs a second Gemini pass on the same bundle and produces a downloadable Claude Code plugin zip: skills, slash commands, subagents, lifecycle hooks, MCP build prompts, all bundled with a `plugin.json` manifest and a top-level README that explains the install.
- **Load demo cache.** Falls back to a precomputed `data/demo_cache.json` snapshot. Drips synthetic trace events with realistic timings (~6s total) so the agent appears to work even on a flaky network — paper draft + venue card + full trace land instantly afterward.
- **Phase 1 hello-world tab.** One-button `make ping` equivalent. Single LLM round-trip to verify Gateway + Lapdog + Datadog wires are alive before doing a real run.

`make ping` runs the same hello-world call from the command line.
`make precompute URL=https://github.com/owner/repo` refreshes the demo cache.

---

## Project structure

```
agentichack/
  app.py                          Streamlit UI (Pipeline + Phase 1 tabs)
  paperpilot/
    github_ingest.py              PyGithub repo -> ranked file bundle
    llm_ingest.py                 Gemini 1M-ctx -> structured summary
    embed.py                      text-embedding-3-small via Gateway
    cfp_match.py                  cosineDistance venue ranking
    arxiv_lookup.py               citation candidate pre-filter (ClickHouse + arxiv)
    draft.py                      section streaming + citation strip + tiktoken/cost fallback
    skill_extract.py              repo bundle -> structured PluginPack (skills/commands/agents/hooks/mcps) via Gemini
    skill_render.py               PluginPack -> Claude Code plugin directory zip (manifest + dirs + hook scripts)
    nimble_client.py              Nimble Search/Answers/Extract HTTPS client (httpx + trace.step + timeouts)
    clickhouse_client.py          schema + trace_log + session_artifacts (paper/plugin persistence)
    latex_export.py               .tex + .bib assembly
    pipeline.py                   end-to-end orchestrator + demo cache writer (totals rolled up)
    trace.py                      log_event + step context manager + in-process buffer
    gateway.py                    Vercel AI Gateway client (model strings encode provider)
    llm_ping.py                   Phase 1 hello-world helper
  data/
    cfp_seed.json                 41 hand-curated CFPs
    arxiv_seed.json               223 arxiv papers
  scripts/
    seed_clickhouse.py            embed + insert corpora
    fetch_arxiv.py                refresh the arxiv corpus
    demo_precompute.py            DEMO_MODE cache for offline demo
    meta_flex.py                  run PaperPilot on itself
  submission/                     LaTeX output drop
  Makefile                        dev / seed / ping / precompute / meta / push
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

- **Senor Clown** — engineering
- **Nikki** — clinical-ML domain (Arya Health), academic-tone review, ML4H demo realism

Built for the Agentic Engineering Hack NYC at Datadog HQ, sponsored by Datadog, ClickHouse, Nimble, Luminai, and DeepMind.
