"""Idempotent Senso seed for the Outreach workflow.

Creates the six content types the Outreach page needs in the Senso
workspace if they do not already exist. Safe to re-run.

This is separate from `scripts/seed_senso.py`, which ingests tone-reference
exemplars into Senso's Knowledge Base for the paper drafter. Different
goals, different surfaces.

Usage:
    uv run python -m scripts.seed_outreach
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python -m scripts.seed_outreach` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS  # noqa: E402
from paperpilot.outreach.senso import Senso  # noqa: E402


load_dotenv()


def seed_content_types(senso: Senso) -> dict[str, str]:
    """Ensure every required content type exists. Returns name -> id map."""
    existing = {ct["name"]: ct["id"] for ct in senso.list_content_types()}
    ids: dict[str, str] = {}
    for name, config in CONTENT_TYPE_CONFIGS.items():
        if name in existing:
            ids[name] = existing[name]
            continue
        created = senso.create_content_type(name, config)
        ids[name] = created["id"]
    return ids


def main() -> None:
    senso = Senso.from_env()
    ids = seed_content_types(senso)
    print("Senso content types ready:")
    for name, ctid in ids.items():
        print(f"  {name:30s} -> {ctid}")


if __name__ == "__main__":
    main()
