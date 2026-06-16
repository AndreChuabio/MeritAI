"""O-1A evidence ledger over Supabase (Postgres).

Supabase counterpart to ``paperpilot.outreach.evidence`` (which targets
ClickHouse and is owned by another agent). The eight USCIS O-1A criteria,
the per-criterion narrative drafting, and the reportlab PDF dossier are all
reused from the existing pipeline modules; only the data-access layer is
re-implemented here against ``paperpilot.supabase_client.get_conn``.

Key differences from the ClickHouse module:

  * ``o1_evidence`` in Postgres uses real INSERT / UPDATE / DELETE. Deletes
    are HARD deletes -- there is no ``deleted`` tombstone column and no
    ReplacingMergeTree FINAL semantics.
  * Reads and writes are always scoped to the authenticated ``user_id``.

The narrative drafter and PDF builder in the legacy modules call ClickHouse
internally, so they cannot be invoked directly. Instead this service reuses
their pure (DB-free) prompt-assembly and rendering helpers, feeding them the
Supabase-sourced ``EvidenceItem`` / ``UserProfile`` objects.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import date, datetime
from typing import Any, Optional

import psycopg
from reportlab.lib.pagesizes import LETTER

from paperpilot import supabase_client, trace
from paperpilot.gateway import DEFAULTS, get_client
from paperpilot.outreach import dossier as dossier_mod
from paperpilot.outreach import evidence_draft as draft_mod
from paperpilot.outreach.evidence import (
    CRITERION_KEYS,
    USCIS_O1A_CRITERIA,
    EvidenceItem,
)
from paperpilot.outreach.log import UserProfile
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.units import inch

logger = logging.getLogger(__name__)

_VALID_STATUS: set[str] = {"draft", "ready"}

# Mutable columns update_evidence is allowed to touch.
_UPDATABLE_FIELDS: set[str] = {
    "criterion",
    "title",
    "description",
    "evidence_url",
    "evidence_date",
    "status",
    "metadata",
}

_SELECT_COLS = (
    "id, user_id, criterion, title, description, evidence_url, "
    "evidence_date, declared_at, status, metadata"
)


def _validate_criterion(criterion: str) -> None:
    """Raise ValueError if criterion is not one of the eight O-1A keys."""
    if criterion not in CRITERION_KEYS:
        raise ValueError(
            f"unknown criterion {criterion!r}; expected one of "
            f"{sorted(CRITERION_KEYS)}"
        )


def _validate_status(status: str) -> None:
    """Raise ValueError if status is not 'draft' or 'ready'."""
    if status not in _VALID_STATUS:
        raise ValueError(
            f"unknown status {status!r}; expected one of {sorted(_VALID_STATUS)}"
        )


def _row_to_item(row: tuple) -> EvidenceItem:
    """Map a SELECT row (in fixed column order) to an EvidenceItem.

    Postgres returns ``evidence_date`` as a ``date`` or ``None`` directly and
    ``metadata`` already decoded to a dict by psycopg's jsonb adapter, so no
    sentinel or manual JSON parsing is needed.
    """
    (
        id_,
        user_id,
        criterion,
        title,
        description,
        evidence_url,
        evidence_date,
        declared_at,
        status,
        metadata,
    ) = row
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata) if metadata else {}
        except json.JSONDecodeError:
            logger.warning(
                "failed to decode metadata for evidence id=%s; defaulting to {}",
                id_,
            )
            metadata = {}
    return EvidenceItem(
        id=str(id_),
        user_id=str(user_id),
        criterion=criterion,
        title=title,
        description=description,
        evidence_url=evidence_url,
        evidence_date=evidence_date,
        declared_at=declared_at,
        status=status,
        metadata=metadata or {},
    )


def _fetch_one(
    user_id: str, item_id: str, conn: psycopg.Connection | None = None
) -> Optional[EvidenceItem]:
    """Fetch one item by id, scoped to user_id, or None."""
    owns = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        row = conn.execute(
            f"SELECT {_SELECT_COLS} FROM o1_evidence "
            "WHERE user_id = %s AND id = %s",
            (user_id, item_id),
        ).fetchone()
    finally:
        if owns:
            conn.close()
    return _row_to_item(row) if row else None


def list_evidence(
    user_id: str,
    criterion: Optional[str] = None,
    conn: psycopg.Connection | None = None,
) -> list[EvidenceItem]:
    """List a user's evidence items, newest-first by declared_at.

    Optionally filter by criterion.
    """
    if not user_id:
        raise ValueError("user_id is required")
    if criterion is not None:
        _validate_criterion(criterion)

    params: list[Any] = [user_id]
    where = "user_id = %s"
    if criterion is not None:
        where += " AND criterion = %s"
        params.append(criterion)

    owns = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        rows = conn.execute(
            f"SELECT {_SELECT_COLS} FROM o1_evidence "
            f"WHERE {where} ORDER BY declared_at DESC",
            params,
        ).fetchall()
    finally:
        if owns:
            conn.close()
    return [_row_to_item(r) for r in rows]


def evidence_by_criterion(
    user_id: str,
    conn: psycopg.Connection | None = None,
) -> dict[str, list[EvidenceItem]]:
    """Group a user's evidence by criterion.

    Returns a dict keyed by ALL eight criterion keys (empty list values for
    unused criteria), preserving the canonical USCIS_O1A_CRITERIA ordering.
    """
    rows = list_evidence(user_id, conn=conn)
    grouped: dict[str, list[EvidenceItem]] = {k: [] for k, _ in USCIS_O1A_CRITERIA}
    for item in rows:
        if item.criterion in grouped:
            grouped[item.criterion].append(item)
    return grouped


def count_satisfied_criteria(
    user_id: str,
    conn: psycopg.Connection | None = None,
) -> int:
    """Number of distinct criteria with at least one item (0..8)."""
    if not user_id:
        raise ValueError("user_id is required")
    owns = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        row = conn.execute(
            "SELECT count(DISTINCT criterion) FROM o1_evidence WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    finally:
        if owns:
            conn.close()
    return int(row[0]) if row else 0


def declare_evidence(
    user_id: str,
    criterion: str,
    title: str,
    description: str = "",
    evidence_url: str = "",
    evidence_date: Optional[date] = None,
    status: str = "draft",
    metadata: Optional[dict] = None,
    conn: psycopg.Connection | None = None,
) -> EvidenceItem:
    """Insert a new evidence item and return it.

    Raises ValueError if criterion is not one of the eight O-1A keys, status
    is invalid, or required fields are missing.
    """
    _validate_criterion(criterion)
    _validate_status(status)
    if not user_id:
        raise ValueError("user_id is required")
    if not title:
        raise ValueError("title is required")

    owns = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        row = conn.execute(
            "INSERT INTO o1_evidence "
            "(user_id, criterion, title, description, evidence_url, "
            " evidence_date, status, metadata) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            f"RETURNING {_SELECT_COLS}",
            (
                user_id,
                criterion,
                title,
                description,
                evidence_url,
                evidence_date,
                status,
                json.dumps(metadata or {}, default=str),
            ),
        ).fetchone()
    finally:
        if owns:
            conn.close()
    return _row_to_item(row)


def update_evidence(
    user_id: str,
    item_id: str,
    conn: psycopg.Connection | None = None,
    **fields: Any,
) -> EvidenceItem:
    """Update mutable fields of an existing item and return the new state.

    user_id is enforced -- you can only update your own items. Raises
    ValueError if the item is not found for this user, a field name is not
    updatable, or criterion/status values are invalid.
    """
    if not user_id:
        raise ValueError("user_id is required")
    fields = {k: v for k, v in fields.items() if v is not None}
    bad = set(fields) - _UPDATABLE_FIELDS
    if bad:
        raise ValueError(
            f"non-updatable fields: {sorted(bad)}; allowed: {sorted(_UPDATABLE_FIELDS)}"
        )
    if not fields:
        existing = _fetch_one(user_id, item_id, conn=conn)
        if existing is None:
            raise ValueError(
                f"evidence id={item_id!r} not found for user_id={user_id!r}"
            )
        return existing

    if "criterion" in fields:
        _validate_criterion(fields["criterion"])
    if "status" in fields:
        _validate_status(fields["status"])

    set_parts: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key == "metadata":
            set_parts.append("metadata = %s")
            params.append(json.dumps(value or {}, default=str))
        else:
            set_parts.append(f"{key} = %s")
            params.append(value)
    set_parts.append("updated_at = %s")
    params.append(datetime.now())
    params.extend([user_id, item_id])

    owns = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        row = conn.execute(
            f"UPDATE o1_evidence SET {', '.join(set_parts)} "
            f"WHERE user_id = %s AND id = %s RETURNING {_SELECT_COLS}",
            params,
        ).fetchone()
    finally:
        if owns:
            conn.close()
    if row is None:
        raise ValueError(
            f"evidence id={item_id!r} not found for user_id={user_id!r}"
        )
    return _row_to_item(row)


def delete_evidence(
    user_id: str,
    item_id: str,
    conn: psycopg.Connection | None = None,
) -> bool:
    """Hard-delete an item scoped to user_id. Returns True if a row was removed.

    The Postgres o1_evidence table uses a real DELETE (no tombstone column).
    """
    if not user_id:
        raise ValueError("user_id is required")
    owns = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM o1_evidence WHERE user_id = %s AND id = %s",
            (user_id, item_id),
        )
        deleted = cur.rowcount
    finally:
        if owns:
            conn.close()
    return deleted > 0


def _find_user_profile_by_id(
    user_id: str, conn: psycopg.Connection | None = None
) -> Optional[UserProfile]:
    """Load the user's profile row from Supabase, or None.

    Mirrors ``evidence_draft._find_user_profile_by_id`` but reads Postgres.
    Best-effort context; never raises on a missing or malformed row.
    """
    if not user_id:
        return None
    owns = conn is None
    conn = conn or supabase_client.get_conn()
    try:
        row = conn.execute(
            "SELECT user_id, name, title, about, voice_tone, github_url, "
            "linkedin_url, scholar_url, site_url, resume_text "
            "FROM user_profile WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    except Exception as exc:  # noqa: BLE001 -- profile is optional context
        logger.warning("user_profile lookup failed for user_id=%s: %s", user_id, exc)
        return None
    finally:
        if owns:
            conn.close()
    if not row:
        return None
    return UserProfile(
        user_id=str(row[0]),
        name=row[1],
        title=row[2],
        about=row[3],
        voice_tone=row[4],
        github_url=row[5],
        linkedin_url=row[6],
        scholar_url=row[7],
        site_url=row[8],
        resume_text=row[9],
    )


def draft_criterion_narrative(
    user_id: str,
    criterion: str,
    session_id: Optional[str] = None,
) -> str:
    """Draft a petition-quality narrative for one O-1A criterion.

    Reuses the prompt assembly and AI Gateway streaming logic from
    ``paperpilot.outreach.evidence_draft``; only the evidence and profile
    inputs are sourced from Supabase. Returns the finished narrative string.

    Raises ValueError if criterion is unknown, RuntimeError if the LLM call
    fails (no silent fallback).
    """
    if not user_id:
        raise ValueError("user_id is required")
    if criterion not in CRITERION_KEYS:
        raise ValueError(
            f"unknown criterion {criterion!r}; expected one of "
            f"{sorted(CRITERION_KEYS)}"
        )

    conn = supabase_client.get_conn()
    try:
        items = list_evidence(user_id, criterion=criterion, conn=conn)
        profile = _find_user_profile_by_id(user_id, conn=conn)
    finally:
        conn.close()

    # Reuse the pure prompt builders from the legacy drafter so the prompt,
    # system message, and Scholar handling stay identical across both apps.
    user_prompt = draft_mod._build_user_prompt(criterion, items, profile)
    model = DEFAULTS["draft"]
    sid = session_id or f"evidence_draft_{user_id}"

    with trace.step(
        sid,
        f"evidence_draft.{criterion}",
        model=model,
        user_id=user_id,
        criterion=criterion,
        declared_item_count=len(items),
        has_profile=profile is not None,
    ) as ctx:
        try:
            client = get_client()
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": draft_mod._SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                stream_options={"include_usage": True},
                max_tokens=600,
                temperature=0.4,
            )
        except Exception as exc:  # noqa: BLE001 -- re-raise with context
            logger.exception(
                "LLM stream init failed for criterion=%s user=%s",
                criterion,
                user_id,
            )
            raise RuntimeError(
                f"evidence_draft LLM init failed for criterion={criterion!r}: {exc}"
            ) from exc

        chunks: list[str] = []
        final_usage = None
        try:
            for event in stream:
                if getattr(event, "usage", None):
                    final_usage = event.usage
                delta = event.choices[0].delta.content if event.choices else None
                if delta:
                    chunks.append(delta)
        except Exception as exc:  # noqa: BLE001 -- re-raise with context
            logger.exception(
                "LLM stream consume failed for criterion=%s user=%s",
                criterion,
                user_id,
            )
            raise RuntimeError(
                f"evidence_draft LLM stream failed for criterion={criterion!r}: {exc}"
            ) from exc

        full_text = "".join(chunks)
        ctx["chars"] = len(full_text)
        if final_usage:
            ctx["tokens_in"] = final_usage.prompt_tokens
            ctx["tokens_out"] = final_usage.completion_tokens
            gw_cost = getattr(final_usage, "cost", None)
            if gw_cost is not None:
                ctx["cost_usd"] = gw_cost
                ctx["cost_source"] = "gateway"
            else:
                from paperpilot.draft import _estimate_cost

                ctx["cost_usd"] = _estimate_cost(
                    model, final_usage.prompt_tokens, final_usage.completion_tokens
                )
                ctx["cost_source"] = "estimated"
        else:
            from paperpilot.draft import _estimate_cost, _tok_count

            t_in = _tok_count(draft_mod._SYSTEM_PROMPT) + _tok_count(user_prompt)
            t_out = _tok_count(full_text)
            ctx["tokens_in"] = t_in
            ctx["tokens_out"] = t_out
            ctx["cost_usd"] = _estimate_cost(model, t_in, t_out)
            ctx["cost_source"] = "estimated"

    return full_text


def _draft_all_narratives(
    user_id: str,
    grouped: dict[str, list[EvidenceItem]],
    session_id: Optional[str] = None,
) -> dict[str, str]:
    """Materialize all eight narratives sequentially over Supabase evidence.

    Mirrors ``evidence_draft.draft_all_narratives`` but reuses this module's
    Supabase-backed ``draft_criterion_narrative``. Criteria with no declared
    items map to an empty string.
    """
    out: dict[str, str] = {}
    for key, _definition in USCIS_O1A_CRITERIA:
        if not grouped.get(key):
            out[key] = ""
            continue
        out[key] = draft_criterion_narrative(
            user_id=user_id, criterion=key, session_id=session_id
        )
    return out


def build_dossier(user_id: str, session_id: Optional[str] = None) -> bytes:
    """Generate the O-1A dossier PDF for a user from Supabase evidence.

    Reuses the reportlab rendering helpers in
    ``paperpilot.outreach.dossier`` (cover, summary, per-criterion sections,
    footer, styles); only the evidence, satisfied count, profile, and
    narratives are sourced from Supabase.

    Returns the PDF bytes. Raises RuntimeError if narrative drafting or PDF
    rendering fails; no partial / empty bytes are returned.
    """
    if not user_id:
        raise ValueError("user_id is required")

    conn = supabase_client.get_conn()
    try:
        grouped = evidence_by_criterion(user_id, conn=conn)
        satisfied = count_satisfied_criteria(user_id, conn=conn)
        profile = _find_user_profile_by_id(user_id, conn=conn)
    finally:
        conn.close()

    try:
        narratives = _draft_all_narratives(user_id, grouped, session_id=session_id)
    except Exception as exc:  # noqa: BLE001 -- escalate per contract
        raise RuntimeError(
            f"failed to draft O-1A narratives for user_id={user_id!r}"
        ) from exc

    try:
        display_name = (profile.name.strip() if profile and profile.name else "") or user_id
        title_line = (profile.title.strip() if profile and profile.title else "") or None

        styles = dossier_mod._make_styles()
        today = datetime.utcnow().date()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            leftMargin=1.0 * inch,
            rightMargin=1.0 * inch,
            topMargin=1.0 * inch,
            bottomMargin=1.0 * inch,
            title="O-1A Evidence Dossier",
            author=display_name,
        )

        story: list = []
        story.extend(
            dossier_mod._cover_flowables(
                user_id, display_name, title_line, styles, today
            )
        )
        story.extend(dossier_mod._summary_flowables(satisfied, styles))

        for idx, (key, label) in enumerate(USCIS_O1A_CRITERIA, start=1):
            items = grouped.get(key, [])
            narrative = (narratives.get(key) or "").strip()
            story.extend(
                dossier_mod._criterion_section_flowables(
                    idx, key, label, items, narrative, styles
                )
            )

        doc.build(
            story,
            onFirstPage=dossier_mod._on_page,
            onLaterPages=dossier_mod._on_page,
        )
        pdf_bytes = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001 -- escalate per contract
        raise RuntimeError(
            f"failed to render O-1A dossier PDF for user_id={user_id!r}"
        ) from exc

    if not pdf_bytes:
        raise RuntimeError(
            f"reportlab produced empty PDF bytes for user_id={user_id!r}"
        )
    return pdf_bytes


def dossier_filename(user_id: str) -> str:
    """Return a download filename, reusing the legacy slug + stamp logic."""
    profile = _find_user_profile_by_id(user_id)
    name = profile.name if profile and profile.name else None
    return dossier_mod.dossier_filename(user_id, name)
