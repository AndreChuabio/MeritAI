# LinkedIn post drafts

## Version A — full architecture flex (~280 words)

Spent today at the NYC Agentic Engineering Hack at Datadog HQ. Walked out with something I'm genuinely proud of.

Built "Productionize Your Product" — one agent that helps researchers and engineers turn their work into shipped artifacts:

→ Productize: drop a GitHub repo, get a research paper draft for a real venue (53 Call-for-Papers, curated and live-discovered)
→ Market: same agent drafts personal-brand outreach for talks, collaborations, visa applications
→ Track: aggregates everything into an O-1 and National Interest Waiver progress dashboard scored against USCIS criteria

Cost per paper: under five cents. Built in ~7 hours. Live at paperpilot-production-97dc.up.railway.app.

The architecture story is the part I'm proudest of. Three retrieval systems, zero coupling:
- ClickHouse Cloud — what we own (venue scope embeddings, arxiv corpus, audit log, session artifacts)
- Senso AI — what we license (tone exemplars, brand kit)
- Nimble — what's on the live web (venue deadline verification, prior-art search)

Every LLM call routed through Vercel AI Gateway. Gemini 2.5 Flash for 1M-context repo ingestion. Claude Sonnet 4.6 for section-by-section drafting. Citations gated against the arxiv corpus with a post-hoc regex strip — zero hallucinations in test runs.

Observability via Lapdog locally and Datadog LLM Observability cloud forward in production. One span end-to-end across every API call and DB write.

Massive thanks to Nikki for partnering on the outreach + visa-progress workflow, and to the sponsor teams for shipping the kind of infra that lets two people build this in an afternoon.

Code: github.com/AndreChuabio/agentichack

#AgenticAI #Hackathon #LLMOps

---

## Version B — short, punchy (~120 words)

Closed out the NYC Agentic Engineering Hack at Datadog HQ today.

We built "Productionize Your Product" — one agent that turns your GitHub repo into a research paper draft for a real Call-for-Papers, then drafts your personal-brand outreach for it, then tracks your O-1 visa progress against USCIS criteria. All on the same stack.

Under five cents per paper. Zero hallucinated citations by design. ~7 hours from blank repo to a live URL.

Stack: Vercel AI Gateway + Gemini + Claude + ClickHouse + Senso + Nimble + Datadog Lapdog. Three retrieval systems, zero coupling.

Big thanks to Nikki for partnering on the outreach + visa workflows.

Code: github.com/AndreChuabio/agentichack
Live: paperpilot-production-97dc.up.railway.app

#AgenticAI #Hackathon

---

## Version C — story-first (~200 words)

Two months ago I was a data scientist hunting for the right venue for a side project. Spent three weekends on it. Started the paper draft from a blank Overleaf.

Today at the NYC Agentic Engineering Hack at Datadog HQ, Nikki and I built the agent I wish I'd had — and two more on top of it.

Productionize Your Product:
→ Drop a GitHub repo, get a research paper for a matched conference
→ Same agent drafts your personal-brand outreach for talks, collabs, visas
→ Tracks your O-1 progress against USCIS criteria

Under five cents per paper. Built in ~7 hours.

The architecture I'm proudest of: three retrieval layers with zero coupling. ClickHouse for what we own, Senso for what we license, Nimble for what's on the live web. Every LLM call traced through Datadog Lapdog with a real-time cost pill.

Massive thanks to Nikki for the outreach + immigration-track UX, and to Vercel AI Gateway, ClickHouse, Senso, Nimble, and Datadog for sponsoring the kind of infra two people can stand up an afternoon.

Code: github.com/AndreChuabio/agentichack
Live: paperpilot-production-97dc.up.railway.app

#AgenticAI #Hackathon #LLMOps

---

## Tagging suggestions

People to tag (LinkedIn handles you'd need to look up):
- Nikki (collaborator)
- Andy Tran (organizer)
- Eman Aleem (organizer)
- Shri Subramanian (Datadog GPM, judge)
- Rushikesh Akhare (Luminai, judge)
- Adam Stevens / Justus Santiago (Nimble, judges)
- Zoe Steinkamp / Nataly Merezhuk (ClickHouse, judges)

Companies to tag: Datadog, ClickHouse, Vercel, Anthropic, Google DeepMind, Senso, Nimble (or NimbleWay).
