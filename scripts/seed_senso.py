"""Idempotent Senso workspace seed.

Creates the content types required by the Outreach workflow if they do not
already exist in the workspace. Safe to re-run.

Usage:
    uv run python -m scripts.seed_senso
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python -m scripts.seed_senso` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS  # noqa: E402
from paperpilot.outreach.senso import Senso  # noqa: E402


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
