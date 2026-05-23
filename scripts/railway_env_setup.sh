#!/usr/bin/env bash
# scripts/railway_env_setup.sh
#
# Pushes the .env file into the linked Railway service's environment.
# Run AFTER `railway login` and `railway link` (or `railway init`).
#
# Usage:
#   bash scripts/railway_env_setup.sh

set -euo pipefail

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run from the project root with .env present." >&2
  exit 1
fi

if ! command -v railway >/dev/null 2>&1; then
  echo "ERROR: railway CLI not installed. Run 'npm i -g @railway/cli'." >&2
  exit 1
fi

# Set DD_LLMOBS_AGENTLESS_ENABLED=1 explicitly -- it's required in cloud
# because there's no local Lapdog agent on Railway.
echo "Setting DD_LLMOBS_AGENTLESS_ENABLED=1..."
railway variables --set "DD_LLMOBS_AGENTLESS_ENABLED=1"

# Push every uncommented KEY=VALUE from .env.
while IFS='=' read -r key value; do
  # Skip comments and blank lines.
  if [[ "$key" =~ ^[[:space:]]*# ]] || [[ -z "$key" ]] || [[ -z "${value:-}" ]]; then
    continue
  fi
  # Strip surrounding quotes from value if present.
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  echo "Setting $key..."
  railway variables --set "$key=$value"
done < .env

echo
echo "Done. Verify with: railway variables"
echo "Then deploy: railway up"
