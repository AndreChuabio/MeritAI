"""Apply ClickHouse migrations from the migrations/ folder.

Reads every .sql file in lexicographic order and runs each statement via
the configured ClickHouse client. Migrations are expected to be idempotent
(IF NOT EXISTS / ADD COLUMN IF NOT EXISTS / etc.) so re-running is safe.

Usage:
    uv run python scripts/run_migrations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from paperpilot.clickhouse_client import get_client  # noqa: E402


def _split_statements(sql: str) -> list[str]:
    """Split a SQL file on semicolons, stripping comments and blanks."""
    stripped_lines = [
        line for line in sql.splitlines() if not line.strip().startswith("--")
    ]
    body = "\n".join(stripped_lines)
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


def main() -> int:
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        print(f"No migrations found in {migrations_dir}")
        return 0

    client = get_client()
    for path in files:
        print(f"Applying {path.name}...")
        for stmt in _split_statements(path.read_text()):
            client.command(stmt)
        print(f"  done: {path.name}")

    print(f"\nApplied {len(files)} migration file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
