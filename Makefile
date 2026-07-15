.PHONY: dev dev-traced seed fetch-arxiv ping precompute meta clean push

# Run Streamlit locally with Lapdog wrap. The venv path is explicit so
# Lapdog finds OUR streamlit (which has ddtrace) -- a bare `streamlit`
# would resolve to system anaconda's copy.
dev-local:
	lapdog .venv/bin/streamlit run Productize.py

# Run with Datadog cloud forward as well (LLM Obs trace lands in DD cloud).
# Streamlit loads .env via load_dotenv(); the agentless flag makes ddtrace
# ship directly bypassing Lapdog's port-8126 contention.
dev:
	DD_LLMOBS_AGENTLESS_ENABLED=1 lapdog .venv/bin/streamlit run Productize.py

# Run Streamlit raw, no Lapdog -- for debugging the UI without telemetry.
dev-raw:
	uv run streamlit run Productize.py

# Run the FastAPI backend (Phase 2) with autoreload on :8000.
api:
	uv run uvicorn backend.main:app --reload --port 8000

# Seed ClickHouse with CFP + arxiv corpora.
seed:
	uv run python scripts/seed_clickhouse.py

# Re-fetch arxiv corpus from arxiv.org (~1-2 min).
fetch-arxiv:
	uv run python scripts/fetch_arxiv.py

# One-shot Nimble crawl -> ClickHouse cfp table. Up to 20 fresh venues.
# Requires NIMBLE_API_KEY; no-ops if missing. Longer Nimble timeout because
# broad search queries can take 15-25s upstream.
refresh-corpus:
	NIMBLE_TIMEOUT_S=30 uv run python scripts/refresh_cfp_corpus.py

# Smoke: minimal LLM ping (no UI). Useful before launching the app.
ping:
	uv run python -c "from dotenv import load_dotenv; load_dotenv(); from paperpilot.trace import new_session; from paperpilot.llm_ping import ping; print(ping(new_session('cli')))"

# Ping with Datadog cloud forward via ddtrace-run. Sends one LLM trace to
# Datadog LLM Observability -- this is what the DD signup wizard waits for.
# Requires DD_API_KEY, DD_SITE, DD_LLMOBS_ENABLED=1, DD_LLMOBS_ML_APP in .env.
#
# DD_LLMOBS_AGENTLESS_ENABLED=1 bypasses any local Datadog/Lapdog agent and
# ships the LLM trace directly to DD_SITE. Without this, Lapdog (which holds
# port 8126) intercepts the trace and never forwards it to cloud.
ping-cloud:
	DD_LLMOBS_AGENTLESS_ENABLED=1 \
	  uv run --env-file .env ddtrace-run python -c "from paperpilot.trace import new_session; from paperpilot.llm_ping import ping; print(ping(new_session('cli')))"

# Pre-compute the demo repo's pipeline output for DEMO_MODE fallback.
# Usage: make precompute URL=https://github.com/owner/repo
precompute:
	uv run python scripts/demo_precompute.py $(URL)

# Closing meta-flex move: run Merit on its own repo, save .tex + .bib to submission/
meta:
	uv run python scripts/meta_flex.py

# Push to an existing GitHub repo. Repo creation and visibility are
# deliberate manual steps, not something make push should do.
push:
	@echo "Repo creation is a deliberate manual step. Use: gh repo create <owner>/<name> --<public|private>"
	@echo "To push commits to an existing remote, use: git push"

# Push .env values into the linked Railway service. Run after `railway link`.
railway-env:
	bash scripts/railway_env_setup.sh

# Deploy to Railway. Requires `railway login` + `railway link` first.
railway-deploy:
	railway up --detach

# Tidy local caches.
clean:
	rm -rf __pycache__ paperpilot/__pycache__ scripts/__pycache__ .pytest_cache

# Run the test suite.
test:
	uv run pytest -q

# Idempotently seed Senso content types (workspace: Agentic-hack).
# Requires SENSO_API_KEY in .env.
seed-senso:
	uv run python -m scripts.seed_senso

# Print the outreach demo rehearsal script.
outreach-demo:
	@echo "Outreach demo rehearsal:"
	@echo "  1. Brand tab: confirm pre-synced brand kit for 'Nikki' loads."
	@echo "  2. Outreach tab: pick VISA, type 'apply to keynote at ML4H 2026', Generate."
	@echo "  3. Track tab: confirm score, Scholar climbs to 14/20, drafts list shows."
	@echo ""
	@echo "If anything 500s, fall back to: DEMO_MODE=true make dev."
