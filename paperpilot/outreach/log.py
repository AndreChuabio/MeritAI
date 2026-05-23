"""ClickHouse audit helpers for the Outreach workflow.

All helpers accept an optional `client` kwarg so unit tests can pass a mock.
In normal use the caller omits it and a real ClickHouse client is opened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from paperpilot.clickhouse_client import get_client


@dataclass
class UserProfile:
    user_id: str
    name: str
    title: str
    about: str
    voice_tone: str
    github_url: str
    linkedin_url: str
    scholar_url: str
    site_url: str
    resume_text: str


_USER_PROFILE_COLS = [
    "user_id", "name", "title", "about", "voice_tone",
    "github_url", "linkedin_url", "scholar_url", "site_url",
    "resume_text", "updated_at",
]

_OUTREACH_LOG_COLS = [
    "ts", "user_id", "purpose", "channel",
    "content_type_id", "sample_job_id", "draft_id", "posted",
]


def upsert_user_profile(profile: UserProfile, client: Any | None = None) -> None:
    client = client or get_client()
    row = [
        profile.user_id, profile.name, profile.title, profile.about,
        profile.voice_tone, profile.github_url, profile.linkedin_url,
        profile.scholar_url, profile.site_url, profile.resume_text,
        datetime.now(),
    ]
    client.insert("user_profile", [row], column_names=_USER_PROFILE_COLS)


def log_generate(
    user_id: str,
    purpose: str,
    channel: str,
    content_type_id: str,
    sample_job_id: str,
    client: Any | None = None,
) -> str:
    """Insert a generate-event row. Returns sample_job_id (acts as row id)."""
    client = client or get_client()
    row = [
        datetime.now(),
        user_id, purpose, channel, content_type_id,
        sample_job_id, "", 0,
    ]
    client.insert("outreach_log", [row], column_names=_OUTREACH_LOG_COLS)
    return sample_job_id


def mark_posted(sample_job_id: str, draft_id: str, client: Any | None = None) -> None:
    client = client or get_client()
    # ClickHouse ALTER UPDATE is async but adequate for audit.
    safe_job = sample_job_id.replace("'", "")
    safe_draft = draft_id.replace("'", "")
    client.command(
        "ALTER TABLE outreach_log UPDATE posted = 1, draft_id = "
        f"'{safe_draft}' WHERE sample_job_id = '{safe_job}'"
    )


def count_posted(user_id: str, client: Any | None = None) -> int:
    client = client or get_client()
    result = client.query(
        "SELECT count() FROM outreach_log WHERE user_id = {u:String} AND posted = 1",
        parameters={"u": user_id},
    )
    return int(result.result_rows[0][0])


def total_drafts(user_id: str, client: Any | None = None) -> int:
    """Count of all draft-generated events for a user (posted or not)."""
    client = client or get_client()
    result = client.query(
        "SELECT count() FROM outreach_log WHERE user_id = {u:String}",
        parameters={"u": user_id},
    )
    return int(result.result_rows[0][0])


def count_by_channel(user_id: str, client: Any | None = None) -> dict[str, int]:
    """Return {channel: count} for every channel the user has used."""
    client = client or get_client()
    result = client.query(
        "SELECT channel, count() AS n FROM outreach_log "
        "WHERE user_id = {u:String} GROUP BY channel ORDER BY n DESC",
        parameters={"u": user_id},
    )
    return {row[0]: int(row[1]) for row in result.result_rows}


def count_by_purpose(user_id: str, client: Any | None = None) -> dict[str, int]:
    """Return {purpose: count} across all drafts for a user."""
    client = client or get_client()
    result = client.query(
        "SELECT purpose, count() AS n FROM outreach_log "
        "WHERE user_id = {u:String} GROUP BY purpose ORDER BY n DESC",
        parameters={"u": user_id},
    )
    return {row[0]: int(row[1]) for row in result.result_rows}


def drafts_by_day(user_id: str, client: Any | None = None) -> list[dict]:
    """Return [{'date': 'YYYY-MM-DD', 'count': n}, ...] for the user's drafts."""
    client = client or get_client()
    result = client.query(
        "SELECT toDate(ts) AS d, count() AS n FROM outreach_log "
        "WHERE user_id = {u:String} GROUP BY d ORDER BY d",
        parameters={"u": user_id},
    )
    return [{"date": str(row[0]), "count": int(row[1])} for row in result.result_rows]
