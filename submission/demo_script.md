# Demo Script — PaperPilot / Productionize Your Product

NYC Agentic Engineering Hack, 2026-05-23.

## Pre-flight checklist (do these in the 5 min before stage)

- [ ] Local Streamlit running: `http://localhost:8501` shows Productize page
- [ ] All 3 sidebar pages load (Productize / Market / Track)
- [ ] Lapdog dashboard open in tab 2: `https://lapdog.datadoghq.com`
- [ ] Datadog LLM Obs open in tab 3: `app.datadoghq.eu` → LLM Observability → paperpilot app
- [ ] Production URL warm in tab 4: `https://paperpilot-production-97dc.up.railway.app`
- [ ] GitHub repo open in tab 5: `https://github.com/AndreChuabio/agentichack`
- [ ] `submission/paperpilot.tex` open in tab 6 (meta-flex closing artifact)
- [ ] `demo_cache.json` exists (`ls data/demo_cache.json`) — the offline insurance

---

## 90-second pitch (primary)

| t | Action on screen | What you say |
|---|---|---|
| 0:00 | Title card / Productize tab landing | "Researchers waste weeks finding the right venue, then start their paper from a blank page. Brand-building and visa applications? Another week each. We collapsed all three into one agent." |
| 0:10 | Click nanoGPT chip → Ingest + match venues | "Drop any GitHub repo. Gemini's 1M-context window reads it through Vercel AI Gateway. ClickHouse vector search ranks 53 venues. Nimble Search live-merges fresh ones." |
| 0:25 | Pick ML4H or EMNLP card → Draft button | "Claude streams the paper, section by section. Citations are real — pulled from arxiv, pre-filtered through ClickHouse, post-hoc stripped if the model invents an ID. Zero hallucinations by design." |
| 0:45 | Sidebar → Market page | "Same agentic spine, different output. Market hits a Senso brand-kit knowledge base to draft outreach for talks, collaborations, visa applications. Every draft inherits the user's voice." |
| 1:00 | Sidebar → Track page | "Track aggregates everything into an O-1 and National Interest Waiver progress dashboard — Scholar citations, drafts posted versus drafted, USCIS evidence categories. The researcher publishes, builds their brand, and watches their case fill in." |
| 1:15 | Productize tab → point to right-rail pill + trace | "Cost per paper: under five cents. Every LLM call traced by Lapdog locally, forwarded to Datadog LLM Observability cloud — one span end-to-end. Three retrieval systems with zero coupling: ClickHouse for what we own, Senso for what we license, Nimble for what's on the live web." |
| 1:25 | Open submission/paperpilot.tex in GitHub tab | "And we ran PaperPilot on its own repo. That's the paper it wrote about itself, going to EMNLP 2026 — attached to our Devpost. Live at paperpilot.up.railway.app." |

**Hard stop at 1:30.**

---

## 60-second tightened version (if pressed for time)

| t | Action | Words |
|---|---|---|
| 0:00 | Productize landing | "Researchers spend weeks on venue search, paper drafting, brand-building, and visa progress. We collapsed all four into one agent. Watch." |
| 0:10 | Click chip → Ingest | "Gemini ingests the repo. ClickHouse ranks 53 venues plus live Nimble web hits." |
| 0:25 | Pick venue → Draft | "Claude drafts. Citations are gated against an arxiv corpus — zero hallucinations." |
| 0:40 | Market then Track sidebar | "Same spine drafts outreach, then tracks O-1 visa progress against USCIS criteria." |
| 0:50 | Right rail + Lapdog tab | "Five cents a paper. Every call traced through Datadog Lapdog. ClickHouse for what we own, Senso for what we license, Nimble for the live web." |

---

## 30-second elevator (for a hallway grab)

> "Productionize Your Product is one agent that turns your GitHub repo into a paper draft for a matched conference, then drafts your outreach for it, then tracks your O-1 visa progress against USCIS criteria — all on the same Datadog-traced ClickHouse-backed stack. Five cents per paper. Try it: paperpilot.up.railway.app."

---

## Q&A prep — likely judge questions

**Q: How do you prevent citation hallucinations?**
> Three layers. One, a ClickHouse pre-filter pulls the top-10 closest arxiv papers by embedding similarity to the repo summary — that's the only candidate set. Two, the drafter is prompted to cite only from that approved list. Three, a regex post-strip drops any [arxiv:id] marker not in the approved set and warns the user. Zero hallucinations in our test runs.

**Q: Why ClickHouse over Postgres + pgvector?**
> Three reasons. Vector search via `cosineDistance` is native. The same database handles our 4 jobs — vector ranking, citation pre-filter, audit log, and artifact persistence. And it's analytics-grade for the trace volume we're already accumulating.

**Q: What does Nimble actually do here? Why not just hand-curate?**
> Anti-staleness. Our 41-venue seed is curated, fast, and rots on day one. Nimble Search runs at every query and merges live web hits — you see them with an orange LIVE badge. We also ship a batch refresh script that pulls Nimble into ClickHouse periodically; 12 new venues landed in the corpus today via that path.

**Q: How does Senso fit if you already have ClickHouse?**
> They're parallel stores for different jobs. ClickHouse holds what we own — venues, arxiv, audit. Senso holds tone and brand context — accepted-paper exemplars for Productize, user voice for Market. Neither knows about the other; both feed Claude's prompt.

**Q: Where's Datadog in this?**
> Two places. Lapdog runs locally and captures every LLM call — the dashboard at lapdog.datadoghq.com reads from localhost. In production on Railway we use the agentless mode with `DD_LLMOBS_AGENTLESS_ENABLED=1` to ship the same span to Datadog LLM Observability cloud. Same trace shape end-to-end.

**Q: How much did this cost to build / run?**
> One paper end-to-end runs about five cents through the Vercel AI Gateway, surfaced in the UI in real-time. Gemini ingest is the largest line item at three cents per long-context call; Claude drafts are roughly one cent per section.

**Q: What's not yet production-ready?**
> No authentication, model versions aren't pinned to dated snapshots, and there's no retry on transient provider errors. None block the demo, all noted as v2 work.

**Q: Why a paper draft? Why not just publish to arxiv directly?**
> The human is in the loop. The output is a LaTeX file you open in Overleaf, edit, and submit. We're a co-pilot, not a publisher. Same posture on the visa side — we draft, you sign.

---

## Fallback plan if something breaks live

- **Streamlit hangs on Ingest** → Click "Load demo cache" instead. Sub-second drip animation, full state hydrated.
- **Senso save returns 400** → Skip the save, click "Load My Profile" — that path doesn't write.
- **Nimble timeout** → ClickHouse-only ranking still happens; just don't mention Nimble for that run.
- **Datadog cloud lag** → Use the Lapdog local tab instead. Same data.
- **Network dies entirely** → `DEMO_MODE=true make dev` falls back to cached fixtures.
- **Production URL slow** → Switch to localhost; the architecture story is identical.

---

## Talking points to drop if a judge lingers

1. **The meta-flex**: "We ran PaperPilot on PaperPilot. The paper it wrote about itself is in submission/paperpilot.tex on the GitHub repo."
2. **The cost pill**: "Every component cost is attributable. Gemini ingest, Claude per-section, embeddings, all summed live in the UI."
3. **The Plugin Pack extractor**: "Click Extract Plugin and the same repo produces a drop-in Claude Code plugin — SKILL.md, slash commands, MCP build prompts, agent specs."
4. **Honest observability**: "Cost source is tagged `gateway` or `estimated` per call. When the Gateway doesn't propagate usage on streamed responses, we fall back to tiktoken plus a price table. The UI shows `(est.)` so you know which numbers are real."

---

## Team

- Senor Clown (Andre Chuabio) — engineering, agentic loop, deploy
- Nikki — outreach workflow, Senso integration, immigration-track UX

Built at the Agentic Engineering Hack NYC, 2026-05-23, at Datadog HQ.
