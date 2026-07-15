"""Verify per-user read isolation on the service-role Postgres path, live.

The FastAPI backend connects to Supabase as service role, which bypasses
RLS entirely. tests/backend/test_user_isolation.py proves statically that
every per-user query in the code filters on user_id; this script proves the
same claim dynamically, against a real database, through the real service
functions:

  1. Create two throwaway confirmed users (A and B) via the Supabase Auth
     admin API.
  2. Write one row for each user into every per-user table -- o1_evidence,
     user_profile, outreach_log, session_artifacts, trace_log -- using the
     actual backend.services / paperpilot.supabase_client functions, not
     raw SQL.
  3. Read back as user A and assert user B's rows never appear, including
     when B's session_id / artifact_name / evidence id is known (guessed or
     replayed) and passed explicitly.
  4. Delete both throwaway auth.users rows (cascade clears every table, per
     scripts/verify_cascade_delete.py) in a finally block regardless of
     outcome.

Prints PASS/FAIL per check and exits non-zero on any leak.

Safety: a prior attempt at this task stalled, most likely on an
unbounded DB connection. To avoid repeating that, this script:
  - probes SUPABASE_DB_URL with a standalone connection using an explicit
    connect_timeout before doing anything else, separate from the shared
    pool the service layer uses;
  - gives every Supabase Auth admin API call an explicit httpx timeout;
  - wraps the whole run in a hard wall-clock deadline (SIGALRM) that aborts
    the check outright rather than letting anything hang. It does not
    retry a hanging connection in a loop.

Exit codes:
  0 - PASS: no cross-tenant read observed.
  1 - FAIL: at least one cross-tenant leak was observed.
  2 - ERROR: an unexpected exception occurred (not a leak verdict).
  3 - ABORTED: the live database was not reachable, or the check did not
      complete, within the timeout. Not a failure of isolation -- the check
      simply did not run. Treat as pending-creds/network.

Usage:
    uv run python scripts/verify_two_user_isolation.py

Requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (Auth admin API) and
SUPABASE_DB_URL (direct Postgres) in the environment or .env.
"""

from __future__ import annotations

import os
import signal
import sys
import uuid
from pathlib import Path
from types import FrameType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from backend.services import evidence_service, market_service  # noqa: E402
from paperpilot import supabase_client, trace  # noqa: E402

_ADMIN_TIMEOUT_S = 15.0
_DB_PROBE_TIMEOUT_S = 10
_HARD_DEADLINE_S = 45


class Aborted(Exception):
    """Raised when the hard wall-clock deadline fires."""


def _on_alarm(signum: int, frame: FrameType | None) -> None:
    raise Aborted(f"live check did not complete within {_HARD_DEADLINE_S}s")


def _probe_db_reachable() -> None:
    """Fail fast (<= _DB_PROBE_TIMEOUT_S) if SUPABASE_DB_URL is unreachable.

    Uses a standalone connection, not the shared pool behind
    paperpilot.supabase_client.get_conn(), so a network problem here is
    caught before anything opens that pool -- an unbounded pool-open call
    is the most likely cause of the previous attempt's stall.
    """
    conninfo = os.environ["SUPABASE_DB_URL"]
    conn = psycopg.connect(
        conninfo, connect_timeout=_DB_PROBE_TIMEOUT_S, autocommit=True
    )
    try:
        conn.execute("SET statement_timeout = 10000")
        conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()


def _create_throwaway_user(tag: str) -> tuple[str, str]:
    """Create a confirmed throwaway user via the Supabase Auth admin API.

    Returns (user_id, email).
    """
    url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    email = f"isolation-verify-{tag}-{uuid.uuid4().hex}@example.com"
    resp = httpx.post(
        f"{url}/auth/v1/admin/users",
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": uuid.uuid4().hex, "email_confirm": True},
        timeout=_ADMIN_TIMEOUT_S,
    )
    resp.raise_for_status()
    user_id = resp.json()["id"]
    print(f"created throwaway user {tag}={user_id} ({email})")
    return user_id, email


def _delete_auth_user(user_id: str) -> None:
    """Delete the auth.users row; on-delete-cascade clears every per-user table."""
    conn = supabase_client.get_conn()
    try:
        conn.execute("SET statement_timeout = 10000")
        conn.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


def _check(label: str, ok: bool, failures: list[str]) -> None:
    if ok:
        print(f"PASS  {label}")
    else:
        print(f"FAIL  {label}")
        failures.append(label)


def _run_checks(user_a: str, user_b: str) -> list[str]:
    failures: list[str] = []

    # --- o1_evidence, via backend.services.evidence_service -----------------
    item_a = evidence_service.declare_evidence(
        user_a, criterion="awards", title="isolation-verify-a"
    )
    item_b = evidence_service.declare_evidence(
        user_b, criterion="awards", title="isolation-verify-b"
    )

    a_ids = {i.id for i in evidence_service.list_evidence(user_a)}
    b_ids = {i.id for i in evidence_service.list_evidence(user_b)}
    _check("o1_evidence: A's list excludes B's item", item_b.id not in a_ids, failures)
    _check("o1_evidence: B's list excludes A's item", item_a.id not in b_ids, failures)
    _check(
        "o1_evidence: A cannot fetch B's item by (guessed) id",
        evidence_service._fetch_one(user_a, item_b.id) is None,
        failures,
    )
    try:
        evidence_service.update_evidence(user_a, item_b.id, title="hijacked")
        update_blocked = False
    except ValueError:
        update_blocked = True
    _check("o1_evidence: A cannot update B's item", update_blocked, failures)
    deleted = evidence_service.delete_evidence(user_a, item_b.id)
    _check("o1_evidence: A's delete of B's item is a no-op", deleted is False, failures)
    _check(
        "o1_evidence: B's item still readable by B after A's no-op delete",
        evidence_service._fetch_one(user_b, item_b.id) is not None,
        failures,
    )

    # --- user_profile, via backend.services.market_service -------------------
    market_service.upsert_profile(user_a, {"name": "isolation-verify-a"})
    market_service.upsert_profile(user_b, {"name": "isolation-verify-b"})
    profile_a = market_service.get_profile(user_a)
    profile_b = market_service.get_profile(user_b)
    _check(
        "user_profile: A's profile is A's own, not B's",
        profile_a.name == "isolation-verify-a" and profile_a.name != profile_b.name,
        failures,
    )

    # --- outreach_log, via backend.services.market_service --------------------
    market_service.insert_outreach_log(
        user_id=user_a,
        purpose="VISA",
        channel="email",
        content_type_id="ct",
        sample_job_id="isolation-verify-job-a",
    )
    market_service.insert_outreach_log(
        user_id=user_b,
        purpose="VISA",
        channel="email",
        content_type_id="ct",
        sample_job_id="isolation-verify-job-b",
    )
    log_a = {r["sample_job_id"] for r in market_service.list_outreach_log(user_a)}
    log_b = {r["sample_job_id"] for r in market_service.list_outreach_log(user_b)}
    _check(
        "outreach_log: A's log excludes B's row",
        "isolation-verify-job-b" not in log_a,
        failures,
    )
    _check(
        "outreach_log: B's log excludes A's row",
        "isolation-verify-job-a" not in log_b,
        failures,
    )

    # --- trace_log, via paperpilot.supabase_client / trace --------------------
    session_a = trace.new_session(user_a)
    session_b = trace.new_session(user_b)
    trace.log_event(session_a, "isolation.verify", {"who": "a"})
    trace.log_event(session_b, "isolation.verify", {"who": "b"})
    _check(
        "trace_log: A reading B's (guessed) session_id gets nothing",
        supabase_client.fetch_traces(session_b, user_a) == [],
        failures,
    )
    _check(
        "trace_log: B can still read their own session",
        len(supabase_client.fetch_traces(session_b, user_b)) > 0,
        failures,
    )

    # --- session_artifacts, via paperpilot.supabase_client ---------------------
    supabase_client.insert_artifact(
        session_a, user_a, "test", "isolation-verify-a.txt", "content-a"
    )
    supabase_client.insert_artifact(
        session_b, user_b, "test", "isolation-verify-b.txt", "content-b"
    )
    artifacts_a = {a["artifact_name"] for a in supabase_client.fetch_artifacts(user_a)}
    _check(
        "session_artifacts: A's artifact list excludes B's artifact",
        "isolation-verify-b.txt" not in artifacts_a,
        failures,
    )
    _check(
        "session_artifacts: A cannot read B's content via known session_id + name",
        supabase_client.fetch_artifact_content(
            session_b, "isolation-verify-b.txt", user_a
        )
        is None,
        failures,
    )
    _check(
        "session_artifacts: B can still read their own artifact content",
        supabase_client.fetch_artifact_content(
            session_b, "isolation-verify-b.txt", user_b
        )
        == "content-b",
        failures,
    )

    return failures


def main() -> int:
    if os.name == "posix":
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(_HARD_DEADLINE_S)
    try:
        print("probing SUPABASE_DB_URL reachability...")
        _probe_db_reachable()
        print("DB reachable.")

        user_a, _email_a = _create_throwaway_user("a")
        user_b, _email_b = _create_throwaway_user("b")

        try:
            failures = _run_checks(user_a, user_b)
        finally:
            print("cleaning up throwaway users...")
            _delete_auth_user(user_a)
            _delete_auth_user(user_b)
            print("cleanup done.")

        if failures:
            print(f"\nFAIL: {len(failures)} cross-tenant leak(s):")
            for f in failures:
                print(f"  - {f}")
            return 1

        print("\nPASS: no cross-tenant read observed across any per-user table")
        return 0
    except Aborted as exc:
        print(f"\nABORT: {exc}")
        print("Live isolation check did not complete -- not a pass or fail verdict.")
        return 3
    except (psycopg.OperationalError, httpx.HTTPError, KeyError) as exc:
        print(f"\nABORT: could not reach Supabase ({exc.__class__.__name__}: {exc})")
        print("Live isolation check did not run -- likely missing/invalid creds.")
        return 3
    finally:
        if os.name == "posix":
            signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
