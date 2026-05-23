# PaperPilot

Drop a GitHub repo. Get a research paper draft for a matched Call-for-Papers. Every LLM call traced.

Built at the **Agentic Engineering Hack NYC**, 2026-05-23, at Datadog HQ.

---

## What it does

PaperPilot turns a GitHub repository into a venue-targeted academic paper draft:

1. **Ingest.** Pulls the README, file tree, and a ranked sample of source files from any GitHub repo. Concatenates into a single bundle under a 600K-token cap.
2. **Summarize.** Sends the bundle to Gemini through Vercel AI Gateway (1M-context window). Gets back a structured `ResearchSummary`: problem, contribution, method, results, limitations, keywords.
3. **Match.** Embeds the summary and ranks 41 hand-curated CFPs (NeurIPS, ICLR, ICML, ACL, EMNLP, KDD, CVPR, ML4H, MICCAI, CHIL, AMIA, workshops, journals) in ClickHouse Cloud by semantic fit + deadline proximity.
4. **Draft.** Streams a paper section-by-section through Claude: abstract, intro, related work, method. The related-work section is citation-grounded — the model can only cite arxiv IDs returned by a pre-filter + tool-call gate. Any unsanctioned `[arxiv:...]` marker is stripped post-hoc.
5. **Export.** Downloads as LaTeX + BibTeX, ready to open in Overleaf.

Every LLM call and tool call is captured by **Lapdog** (Datadog's local LLM-observability CLI) and forwarded to Datadog cloud with one env var.

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
| Long-context ingest | Gemini 2.5 via AI Gateway | DeepMind |
| Drafting | Claude Sonnet 4.6 via AI Gateway | Vercel AI Gateway |
| Vector search + audit log | ClickHouse Cloud | ClickHouse |
| Citation grounding | arxiv API + ClickHouse pre-filter | (anti-hallucination) |
| Demo venue | ML4H 2026 | (clinical-ML authenticity) |

---

## Quickstart

```bash
# 0. Prereqs: macOS, uv, brew, gh CLI, Vercel CLI.

# 1. Install dependencies
uv sync
brew install datadog/lapdog/lapdog

# 2. Configure
cp .env.example .env
# Fill in: AI_GATEWAY_API_KEY, DD_API_KEY, CLICKHOUSE_*

# 3. Seed corpora into ClickHouse (CFPs + arxiv embeddings)
make seed

# 4. Launch
make dev
# -> http://localhost:8501  (Streamlit UI)
# -> http://localhost:8126  (Lapdog dashboard)
# -> Datadog APM (cloud) shows the same session via DD_API_KEY forward
```

`make ping` runs a minimum hello-world LLM call to verify the wires before launching the full UI.

---

## Project structure

```
agentichack/
  app.py                          Streamlit UI (Pipeline + Phase 1 tabs)
  paperpilot/
    github_ingest.py              PyGithub repo -> ranked file bundle
    llm_ingest.py                 Gemini 1M-ctx -> structured summary
    embed.py                      text-embedding-3-small via Gateway
    clickhouse_client.py          schema + trace_log helpers
    cfp_match.py                  cosineDistance venue ranking
    arxiv_lookup.py               citation candidate pre-filter + tool
    draft.py                      section-by-section streaming + citation gate
    latex_export.py               .tex + .bib assembly
    pipeline.py                   end-to-end orchestrator
    trace.py                      log_event + step context manager
    gateway.py                    Vercel AI Gateway client
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

Three layers of defense against hallucinated citations in the related-work section:

1. **Candidate pre-filter (ClickHouse).** Embed the repo summary, fetch the top-10 closest arxiv IDs from the corpus. The model sees only these as approved citations.
2. **Tool gate.** The drafter must call `lookup_paper(arxiv_id)` to read any candidate before citing it.
3. **Post-hoc strip.** Regex `\[arxiv:([^\]]+)\]` scans the output; any ID not in the approved + looked-up set is removed and the sentence flagged.

Result: zero hallucinated citations even if the model tries.

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
