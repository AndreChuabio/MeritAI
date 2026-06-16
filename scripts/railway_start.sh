#!/usr/bin/env bash
# Railway start dispatcher.
#
# One repo, two services, one shared railway.toml. SERVICE_KIND selects which
# process to run. It defaults to the legacy Streamlit app, so the existing
# service is unaffected when the variable is unset; the FastAPI backend service
# sets SERVICE_KIND=api.
set -euo pipefail

if [ "${SERVICE_KIND:-streamlit}" = "api" ]; then
  exec uv run uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi

exec uv run ddtrace-run streamlit run Productize.py \
  --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true
