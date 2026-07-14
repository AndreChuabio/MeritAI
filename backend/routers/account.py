"""Data export and account deletion.

Merit holds immigration evidence, which is sensitive personal data for users who
are predominantly not US nationals. Getting it out and getting it deleted are
obligations that exist whether or not anyone is paying us.

Deletion removes the auth.users row; every per-user table declares
`references auth.users(id) on delete cascade`, so the cascade does the rest. The
test suite in tests/backend/test_account.py mocks the data layer to prove the
routes are wired correctly; scripts/verify_cascade_delete.py proves the cascade
itself against a live database rather than trusting the schema comment.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from backend.auth import AuthUser, CurrentUser
from paperpilot import supabase_client

router = APIRouter(prefix="/account", tags=["account"])


def _rows(conn: Any, sql: str, user_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(sql, (user_id,))
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _collect_user_data(user_id: str) -> dict[str, Any]:
    """Return every row Merit holds for this user, grouped by table.

    session_artifacts content is deliberately excluded from the export (it
    holds base64 zips and full LaTeX, which would make the export enormous);
    metadata is exported and the content is retrievable via the existing
    artifact endpoint.
    """
    conn = supabase_client.get_conn()
    try:
        profile = _rows(conn, "SELECT * FROM user_profile WHERE user_id = %s", user_id)
        return {
            "profile": profile[0] if profile else None,
            "evidence": _rows(
                conn, "SELECT * FROM o1_evidence WHERE user_id = %s", user_id
            ),
            "outreach_log": _rows(
                conn, "SELECT * FROM outreach_log WHERE user_id = %s", user_id
            ),
            "artifacts": _rows(
                conn,
                "SELECT id, session_id, artifact_kind, content_hash, metadata, ts "
                "FROM session_artifacts WHERE user_id = %s",
                user_id,
            ),
        }
    finally:
        conn.close()


def _delete_user(user_id: str) -> None:
    """Delete the auth.users row, cascading to every per-user table."""
    conn = supabase_client.get_conn()
    try:
        conn.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


@router.get("/export")
def export_account(user: AuthUser = CurrentUser) -> dict[str, Any]:
    """Return everything Merit stores about the caller."""
    return _collect_user_data(user.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: AuthUser = CurrentUser) -> Response:
    """Delete the caller's account and all data keyed to it."""
    _delete_user(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
