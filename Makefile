.PHONY: dev dev-traced seed fetch-arxiv ping precompute meta clean push

# Run Streamlit locally with Lapdog wrap + Datadog cloud forward.
dev:
	DD_API_KEY=$$DD_API_KEY lapdog streamlit run app.py

# Same as dev but without the cloud forward (local Lapdog dashboard only).
dev-local:
	lapdog streamlit run app.py

# Run Streamlit raw, no Lapdog -- for debugging the UI without telemetry.
dev-raw:
	uv run streamlit run app.py

# Seed ClickHouse with CFP + arxiv corpora.
seed:
	uv run python scripts/seed_clickhouse.py

# Re-fetch arxiv corpus from arxiv.org (~1-2 min).
fetch-arxiv:
	uv run python scripts/fetch_arxiv.py

# Smoke: minimal LLM ping (no UI). Useful before launching the app.
ping:
	uv run python -c "from dotenv import load_dotenv; load_dotenv(); from paperpilot.trace import new_session; from paperpilot.llm_ping import ping; print(ping(new_session()))"

# Ping with Datadog cloud forward via ddtrace-run. Sends one LLM trace to
# Datadog LLM Observability -- this is what the DD signup wizard waits for.
# Requires DD_API_KEY, DD_SITE, DD_LLMOBS_ENABLED=1, DD_LLMOBS_ML_APP in .env.
ping-cloud:
	uv run ddtrace-run python -c "from dotenv import load_dotenv; load_dotenv(); from paperpilot.trace import new_session; from paperpilot.llm_ping import ping; print(ping(new_session()))"

# Pre-compute the demo repo's pipeline output for DEMO_MODE fallback.
# Usage: make precompute URL=https://github.com/owner/repo
precompute:
	uv run python scripts/demo_precompute.py $(URL)

# Closing meta-flex move: run PaperPilot on its own repo, save .tex + .bib to submission/
meta:
	uv run python scripts/meta_flex.py

# Push to a new public GitHub repo (hackathon -> Devpost needs public).
push:
	gh repo create AndreChuabio/agentichack --public --source=. --push \
	  --description "Drop a GitHub repo. Get a research paper draft. Built at NYC Agentic Engineering Hack 2026 at Datadog HQ."

# Tidy local caches.
clean:
	rm -rf __pycache__ paperpilot/__pycache__ scripts/__pycache__ .pytest_cache
