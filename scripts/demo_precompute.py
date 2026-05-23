"""Pre-compute the demo repo's full pipeline output for DEMO_MODE fallback.

Run once at ~15:00 with the locked demo URL. The Streamlit app reads
data/demo_cache.json when DEMO_MODE=true (Wi-Fi-failure insurance).

Usage:
    uv run python scripts/demo_precompute.py <github_repo_url>
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from paperpilot.pipeline import write_demo_cache


def main() -> None:
    load_dotenv()
    if len(sys.argv) < 2:
        print("usage: uv run python scripts/demo_precompute.py <github_repo_url>")
        sys.exit(1)
    url = sys.argv[1]
    out = write_demo_cache(url)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
