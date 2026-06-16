"""Market service: user profile + outreach drafting over Supabase.

Ports the profile and outreach_log persistence from the legacy ClickHouse
helpers in paperpilot.outreach.log to Supabase Postgres, and wraps the
existing outreach orchestrator so generation logic is reused unchanged. Only
the data layer moves; LLM/Senso logic stays in paperpilot.outreach.*.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from paperpilot import supabase_client, trace
from paperpilot.outreach.orchestrator import DraftCard, generate_drafts
from paperpilot.outreach.purpose import Purpose
from paperpilot.outreach.senso import Senso

# Profile columns in upsert order. updated_at is set by the writer.
_PROFILE_FIELDS = [
    "name", "title", "about", "voice_tone",
    "github_url", "linkedin_url", "scholar_url", "site_url", "resume_text",
]


@dataclass
class Profile:
    """A user's outreach profile. Empty strings are the schema defaults."""

    user_id: str
    name: str = ""
    title: str = ""
    about: str = ""
    voice_tone: str = ""
    github_url: str = ""
    linkedin_url: str = ""
    scholar_url: str = ""
    site_url: str = ""
    resume_text: str = ""


class _LogAdapter:
    """Adapter exposing log_generate so the orchestrator can record events.

    The orchestrator calls logger.log_generate(...); we forward to the
    Supabase writer. Holding the user_id and a shared connection keeps each
    insert cheap and correctly scoped.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def log_generate(
        self,
        user_id: str,
        purpose: str,
        channel: str,
        content_type_id: str,
        sample_job_id: str,
    ) -> str:
        """Insert one generate-event row; return the sample_job_id."""
        insert_outreach_log(
            user_id=user_id,
            purpose=purpose,
            channel=channel,
            content_type_id=content_type_id,
            sample_job_id=sample_job_id,
            conn=self._conn,
        )
        return sample_job_id


def get_profile(user_id: str, conn: Any | None = None) -> Profile:
    """Return the user's profile, or empty defaults if none exists."""
    own_conn = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, title, about, voice_tone, github_url, "
                "linkedin_url, scholar_url, site_url, resume_text "
                "FROM user_profile WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    finally:
        if own_conn:
            conn.close()
    if row is None:
        return Profile(user_id=user_id)
    return Profile(user_id=user_id, **dict(zip(_PROFILE_FIELDS, row)))


def upsert_profile(
    user_id: str, fields: dict[str, Any], conn: Any | None = None
) -> Profile:
    """Upsert the caller's profile row keyed on user_id.

    Only known profile fields are written; unknown keys are ignored. Missing
    fields fall back to the schema default (empty string) on insert and are
    left unchanged on update.
    """
    own_conn = conn is None
    conn = conn or supabase_client.get_conn()
    clean = {k: str(fields[k]) for k in _PROFILE_FIELDS if fields.get(k) is not None}
    cols = ["user_id", *clean.keys(), "updated_at"]
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(
        f"{col} = excluded.{col}" for col in (*clean.keys(), "updated_at")
    )
    values: list[Any] = [user_id, *clean.values(), datetime.now()]
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO user_profile ({', '.join(cols)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT (user_id) DO UPDATE SET {updates}",
                values,
            )
    finally:
        if own_conn:
            conn.close()
    return get_profile(user_id)


def insert_outreach_log(
    user_id: str,
    purpose: str,
    channel: str,
    content_type_id: str,
    sample_job_id: str,
    draft_id: str = "",
    posted: bool = False,
    conn: Any | None = None,
) -> None:
    """Insert one outreach_log row scoped to user_id."""
    own_conn = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO outreach_log "
                "(user_id, purpose, channel, content_type_id, "
                "sample_job_id, draft_id, posted) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id, purpose, channel, content_type_id,
                    sample_job_id, draft_id, posted,
                ),
            )
    finally:
        if own_conn:
            conn.close()


def list_outreach_log(
    user_id: str, limit: int = 50, conn: Any | None = None
) -> list[dict[str, Any]]:
    """Return the user's most recent outreach_log rows, newest first."""
    own_conn = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ts, purpose, channel, content_type_id, "
                "sample_job_id, draft_id, posted FROM outreach_log "
                "WHERE user_id = %s ORDER BY ts DESC LIMIT %s",
                (user_id, limit),
            )
            rows = cur.fetchall()
    finally:
        if own_conn:
            conn.close()
    return [
        {
            "id": r[0],
            "ts": r[1].isoformat() if r[1] is not None else None,
            "purpose": r[2],
            "channel": r[3],
            "content_type_id": r[4],
            "sample_job_id": r[5],
            "draft_id": r[6],
            "posted": r[7],
        }
        for r in rows
    ]


def generate_outreach(
    user_id: str, purpose: str, context: str
) -> list[dict[str, Any]]:
    """Generate outreach draft cards for a purpose and log each event.

    Reuses paperpilot.outreach.orchestrator.generate_drafts for all LLM and
    Senso work; this layer only supplies a Supabase-backed logger and opens a
    session. Senso may be unconfigured: if SENSO_API_KEY is missing we return
    one error card per nothing-generated rather than raising, so the UI can
    surface a clear message.
    """
    try:
        purpose_enum = Purpose(purpose)
    except ValueError as exc:
        raise ValueError(f"Unknown purpose: {purpose!r}") from exc

    if not os.environ.get("SENSO_API_KEY"):
        return [
            asdict(
                DraftCard(
                    channel="",
                    content_type_id="",
                    sample_job_id="",
                    markdown="",
                    error="Senso is not configured (SENSO_API_KEY missing).",
                )
            )
        ]

    senso = Senso.from_env()
    session_id = trace.new_session(user_id)
    conn = supabase_client.get_conn()
    try:
        logger = _LogAdapter(conn)
        cards = generate_drafts(
            senso=senso,
            purpose=purpose_enum,
            context=context,
            session_id=session_id,
            user_id=user_id,
            logger=logger,
        )
    finally:
        conn.close()
    return [asdict(card) for card in cards]
