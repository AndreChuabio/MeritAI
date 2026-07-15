"""Public seed data must not attribute fabricated work to real people."""

import json
from pathlib import Path

# Real people whose names must never appear in demo/fixture data that ships
# publicly. Fabricated citations attached to a real name are a defamation and
# consent problem, not a styling one.
REAL_NAMES = {"Nikki Hu", "Andre Chuabio"}


def test_scholar_seed_names_no_real_people():
    raw = Path("data/scholar_seed.json").read_text()
    for name in REAL_NAMES:
        assert name not in raw, (
            f"{name!r} appears in data/scholar_seed.json, which ships publicly "
            "and contains fabricated citations."
        )
