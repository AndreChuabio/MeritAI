"""Meta-flex closing move: run PaperPilot on the PaperPilot repo itself.

Outputs `submission/paperpilot.tex` and `submission/references.bib` to attach
to the Devpost submission. Run at ~16:10 once Phase 4 is GO.

Usage:
    uv run python scripts/meta_flex.py [github_repo_url]

If no URL is passed, defaults to the repo this script lives in (assuming
we've pushed to github.com/AndreChuabio/agentichack by then).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from paperpilot import trace  # noqa: E402
from paperpilot.draft import draft_paper  # noqa: E402
from paperpilot.github_ingest import fetch_repo  # noqa: E402
from paperpilot.latex_export import export_paper  # noqa: E402
from paperpilot.llm_ingest import summarize_repo  # noqa: E402
from paperpilot.cfp_match import rank_venues  # noqa: E402


SUBMISSION_DIR = Path(__file__).resolve().parent.parent / "submission"


def _default_url() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "https://github.com/AndreChuabio/agentichack"


def main() -> None:
    load_dotenv()
    url = sys.argv[1] if len(sys.argv) > 1 else _default_url()
    print(f"Running PaperPilot on: {url}")

    sid = trace.new_session("system")

    print("  [1/4] ingesting repo...")
    bundle = fetch_repo(url)
    print(f"        {bundle.file_count} files, {bundle.total_tokens:,} tokens")

    print("  [2/4] summarizing via Gemini...")
    summary = summarize_repo(bundle, sid)

    print("  [3/4] matching venues...")
    venues = rank_venues(summary, sid, limit=5)
    if not venues:
        print("  !! no venue matches in horizon; falling back to ML4H 2026 manually")
        from paperpilot.cfp_match import VenueMatch
        from datetime import date

        venues = [
            VenueMatch(
                id="ml4h2026-main",
                name="ML4H 2026",
                scope="ML for Health",
                deadline=date(2026, 7, 4),
                url="https://ml4h.cc/2026",
                fit_score=0.9,
                days_until_deadline=42,
            )
        ]
    venue = venues[0]
    print(f"        top venue: {venue.name} (fit={venue.fit_score:.3f})")

    print("  [4/4] drafting paper sections...")
    sections = {}
    gen = draft_paper(summary, venue, sid)
    try:
        while True:
            section, _delta = next(gen)
            print(".", end="", flush=True)
    except StopIteration as stop:
        sections = stop.value
    print()

    tex, bib = export_paper(summary, venue, sections, authors="Senor Clown and Nikki")
    SUBMISSION_DIR.mkdir(exist_ok=True)
    (SUBMISSION_DIR / "paperpilot.tex").write_text(tex)
    (SUBMISSION_DIR / "references.bib").write_text(bib)
    summary_path = SUBMISSION_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary.model_dump(), indent=2))

    print()
    print(f"wrote {SUBMISSION_DIR / 'paperpilot.tex'}")
    print(f"wrote {SUBMISSION_DIR / 'references.bib'} ({len(bib)} bytes)")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
