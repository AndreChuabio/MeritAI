"""Verify that deleting an auth.users row actually cascades to every per-user
table, rather than trusting the `on delete cascade` schema declaration.

Merit holds immigration evidence for users who are predominantly not US
nationals. A user who deletes their account needs their data gone, not just
"probably gone because the foreign key says so." This script proves it
against a real database:

  1. Create a throwaway confirmed user via the Supabase Auth admin API.
  2. Insert one row into each per-user table for that user_id:
     user_profile, o1_evidence, outreach_log, session_artifacts, trace_log.
  3. Delete the auth.users row directly (the same statement
     backend.routers.account._delete_user runs).
  4. Assert every table has zero rows for that user_id. Print PASS/FAIL per
     table.

Exits non-zero if any table retains rows after the delete, or if any step
fails outright.

Usage:
    uv run python scripts/verify_cascade_delete.py

Requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (for the admin user-create
call) and SUPABASE_DB_URL (for the direct Postgres delete + row checks) in
the environment or .env.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from paperpilot import supabase_client  # noqa: E402

# (table, insert_sql, count_sql) for every table with an
# `on delete cascade` FK to auth.users(id).
_TABLES: list[tuple[str, str, str]] = [
    (
        "user_profile",
        "INSERT INTO user_profile (user_id) VALUES (%s)",
        "SELECT count(*) FROM user_profile WHERE user_id = %s",
    ),
    (
        "o1_evidence",
        "INSERT INTO o1_evidence (user_id, criterion, title) "
        "VALUES (%s, 'awards', 'cascade-verify')",
        "SELECT count(*) FROM o1_evidence WHERE user_id = %s",
    ),
    (
        "outreach_log",
        "INSERT INTO outreach_log (user_id, purpose, channel) "
        "VALUES (%s, 'cascade-verify', 'test')",
        "SELECT count(*) FROM outreach_log WHERE user_id = %s",
    ),
    (
        "session_artifacts",
        "INSERT INTO session_artifacts (session_id, user_id, artifact_kind) "
        "VALUES ('cascade-verify-session', %s, 'test')",
        "SELECT count(*) FROM session_artifacts WHERE user_id = %s",
    ),
    (
        "trace_log",
        "INSERT INTO trace_log (session_id, user_id, kind) "
        "VALUES ('cascade-verify-session', %s, 'test')",
        "SELECT count(*) FROM trace_log WHERE user_id = %s",
    ),
]


def _create_throwaway_user() -> str:
    """Create a confirmed throwaway user via the Supabase Auth admin API.

    Returns the new user's id (a UUID string). A direct INSERT into
    auth.users would need to satisfy Auth's internal invariants (identities
    row, hashed password, instance_id, ...) by hand; the admin API is the
    supported way to create a real, valid auth user.
    """
    url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    email = f"cascade-verify-{uuid.uuid4().hex}@example.com"
    resp = httpx.post(
        f"{url}/auth/v1/admin/users",
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "password": uuid.uuid4().hex,
            "email_confirm": True,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    user_id = resp.json()["id"]
    print(f"created throwaway user {user_id} ({email})")
    return user_id


def _delete_auth_user(user_id: str) -> None:
    """Delete the auth.users row exactly as backend.routers.account does."""
    conn = supabase_client.get_conn()
    try:
        conn.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    user_id = _create_throwaway_user()

    conn = supabase_client.get_conn()
    try:
        for table, insert_sql, _count_sql in _TABLES:
            conn.execute(insert_sql, (user_id,))
            conn.commit()
        print(f"seeded one row into each of {len(_TABLES)} per-user tables")

        seeded_counts = {}
        for table, _insert_sql, count_sql in _TABLES:
            seeded_counts[table] = conn.execute(count_sql, (user_id,)).fetchone()[0]
        missing = [t for t, n in seeded_counts.items() if n < 1]
        if missing:
            print(f"FAIL: seed step did not insert into: {missing}")
            return 1
    finally:
        conn.close()

    _delete_auth_user(user_id)
    print(f"deleted auth.users row for {user_id}")

    conn = supabase_client.get_conn()
    failures: list[str] = []
    try:
        for table, _insert_sql, count_sql in _TABLES:
            remaining = conn.execute(count_sql, (user_id,)).fetchone()[0]
            if remaining == 0:
                print(f"PASS  {table}: 0 rows remain")
            else:
                print(f"FAIL  {table}: {remaining} row(s) remain")
                failures.append(table)
    finally:
        conn.close()

    if failures:
        print(f"\nFAIL: cascade did not clear {failures}")
        return 1

    print("\nPASS: cascade delete cleared every per-user table")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
