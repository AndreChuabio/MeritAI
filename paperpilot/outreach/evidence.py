"""USCIS O-1A evidence ledger CRUD over ClickHouse.

Backs the Track page's "X of 8 satisfied" panel. Each row is one piece
of evidence the user has declared against one of the eight O-1A criteria.

Storage uses a ReplacingMergeTree keyed on (user_id, criterion, id) with
updated_at as the version column. Updates and deletes are implemented as
inserts of a new version; reads dedupe with FINAL and filter deleted = 0.
ALTER UPDATE / DELETE are deliberately avoided per the audit.

The eight criteria here are the O-1A (science-track) set. The artistic
"display of work at exhibitions" criterion (O-1B) is intentionally
omitted; fork this module if O-1B is ever needed.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from clickhouse_connect.driver.client import Client

from paperpilot.clickhouse_client import get_client

logger = logging.getLogger(__name__)


USCIS_O1A_CRITERIA: list[tuple[str, str]] = [
    (
        "awards",
        "Receipt of nationally or internationally recognized prizes or awards for excellence",
    ),
    (
        "membership",
        "Membership in associations that require outstanding achievement",
    ),
    (
        "media_about",
        "Published material about you in professional or major trade publications or major media",
    ),
    (
        "judging",
        "Judging the work of others in your field (peer review, panels, awards)",
    ),
    (
        "original_contributions",
        "Original scientific, scholarly, or business-related contributions of major significance",
    ),
    (
        "scholarly_articles",
        "Authorship of scholarly articles in professional journals or major media",
    ),
    (
        "critical_role",
        "Leading or critical role for organizations with a distinguished reputation",
    ),
    (
        "high_salary",
        "Commanding a high salary or other significantly high remuneration",
    ),
]

CRITERION_KEYS: set[str] = {k for k, _ in USCIS_O1A_CRITERIA}

_VALID_STATUS: set[str] = {"draft", "ready"}

# Sentinel mapped to/from None for evidence_date.
_DATE_SENTINEL: date = date(1970, 1, 1)

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


@dataclass
class EvidenceItem:
    """One declared piece of O-1A evidence for one user."""

    id: str
    user_id: str
    criterion: str
    title: str
    description: str
    evidence_url: str
    evidence_date: Optional[date]
    declared_at: datetime
    status: str
    metadata: dict = field(default_factory=dict)


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
    """Map a SELECT row (in fixed column order) to an EvidenceItem."""
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
        metadata_str,
    ) = row
    ev_date: Optional[date] = None
    if isinstance(evidence_date, date) and evidence_date != _DATE_SENTINEL:
        ev_date = evidence_date
    try:
        metadata = json.loads(metadata_str) if metadata_str else {}
    except json.JSONDecodeError:
        logger.warning("failed to decode metadata for evidence id=%s; defaulting to {}", id_)
        metadata = {}
    return EvidenceItem(
        id=id_,
        user_id=user_id,
        criterion=criterion,
        title=title,
        description=description,
        evidence_url=evidence_url,
        evidence_date=ev_date,
        declared_at=declared_at,
        status=status,
        metadata=metadata,
    )


_SELECT_COLS = (
    "id, user_id, criterion, title, description, evidence_url, "
    "evidence_date, declared_at, status, metadata"
)


def _fetch_one(
    user_id: str, item_id: str, client: Client | None = None
) -> Optional[EvidenceItem]:
    """Fetch the latest non-deleted version of one item, or None."""
    client = client or get_client()
    sql = (
        f"SELECT {_SELECT_COLS} FROM o1_evidence FINAL "
        "WHERE user_id = {uid:String} AND id = {iid:String} AND deleted = 0"
    )
    result = client.query(sql, parameters={"uid": user_id, "iid": item_id})
    if not result.result_rows:
        return None
    return _row_to_item(result.result_rows[0])


def declare_evidence(
    user_id: str,
    criterion: str,
    title: str,
    description: str,
    evidence_url: str = "",
    evidence_date: Optional[date] = None,
    status: str = "draft",
    metadata: Optional[dict] = None,
    client: Client | None = None,
) -> str:
    """Insert a new evidence item.

    Returns the new id (UUID4 string). Raises ValueError if criterion is
    not one of the eight O-1A keys, or status is not 'draft'/'ready'.
    """
    _validate_criterion(criterion)
    _validate_status(status)
    if not user_id:
        raise ValueError("user_id is required")

    client = client or get_client()
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ev_date = evidence_date if evidence_date is not None else _DATE_SENTINEL

    client.insert(
        "o1_evidence",
        [
            [
                item_id,
                user_id,
                criterion,
                title,
                description,
                evidence_url,
                ev_date,
                now,
                status,
                json.dumps(metadata or {}, default=str),
                0,
                now,
            ]
        ],
        column_names=[
            "id",
            "user_id",
            "criterion",
            "title",
            "description",
            "evidence_url",
            "evidence_date",
            "declared_at",
            "status",
            "metadata",
            "deleted",
            "updated_at",
        ],
    )
    return item_id


def update_evidence(
    user_id: str,
    item_id: str,
    client: Client | None = None,
    **fields: Any,
) -> None:
    """Update mutable fields of an existing item.

    Implemented as an insert of a new row with the same id and a fresh
    updated_at; ReplacingMergeTree resolves the latest version on read.
    user_id is enforced -- you can only update your own items.

    Raises ValueError if item_id is not found for this user, or any
    field name is not updatable, or criterion/status values are invalid.
    """
    if not user_id:
        raise ValueError("user_id is required")
    bad = set(fields) - _UPDATABLE_FIELDS
    if bad:
        raise ValueError(
            f"non-updatable fields: {sorted(bad)}; allowed: {sorted(_UPDATABLE_FIELDS)}"
        )

    client = client or get_client()
    current = _fetch_one(user_id, item_id, client=client)
    if current is None:
        raise ValueError(f"evidence id={item_id!r} not found for user_id={user_id!r}")

    if "criterion" in fields:
        _validate_criterion(fields["criterion"])
    if "status" in fields:
        _validate_status(fields["status"])

    merged = {
        "criterion": current.criterion,
        "title": current.title,
        "description": current.description,
        "evidence_url": current.evidence_url,
        "evidence_date": current.evidence_date,
        "status": current.status,
        "metadata": current.metadata,
    }
    merged.update(fields)

    ev_date = merged["evidence_date"] if merged["evidence_date"] is not None else _DATE_SENTINEL
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    client.insert(
        "o1_evidence",
        [
            [
                item_id,
                user_id,
                merged["criterion"],
                merged["title"],
                merged["description"],
                merged["evidence_url"],
                ev_date,
                current.declared_at,
                merged["status"],
                json.dumps(merged["metadata"] or {}, default=str),
                0,
                now,
            ]
        ],
        column_names=[
            "id",
            "user_id",
            "criterion",
            "title",
            "description",
            "evidence_url",
            "evidence_date",
            "declared_at",
            "status",
            "metadata",
            "deleted",
            "updated_at",
        ],
    )


def delete_evidence(
    user_id: str,
    item_id: str,
    client: Client | None = None,
) -> None:
    """Soft-delete via tombstone row (deleted = 1). Idempotent.

    No-op if the item does not exist or is already tombstoned. We never
    issue ALTER DELETE: the ReplacingMergeTree absorbs the tombstone and
    reads filter deleted = 0.
    """
    if not user_id:
        raise ValueError("user_id is required")

    client = client or get_client()
    current = _fetch_one(user_id, item_id, client=client)
    if current is None:
        return

    ev_date = current.evidence_date if current.evidence_date is not None else _DATE_SENTINEL
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    client.insert(
        "o1_evidence",
        [
            [
                item_id,
                user_id,
                current.criterion,
                current.title,
                current.description,
                current.evidence_url,
                ev_date,
                current.declared_at,
                current.status,
                json.dumps(current.metadata or {}, default=str),
                1,
                now,
            ]
        ],
        column_names=[
            "id",
            "user_id",
            "criterion",
            "title",
            "description",
            "evidence_url",
            "evidence_date",
            "declared_at",
            "status",
            "metadata",
            "deleted",
            "updated_at",
        ],
    )


def list_evidence(
    user_id: str,
    criterion: Optional[str] = None,
    client: Client | None = None,
) -> list[EvidenceItem]:
    """List all non-deleted evidence items for a user.

    Optionally filter by criterion. Returns newest-first by declared_at.
    """
    if not user_id:
        raise ValueError("user_id is required")
    if criterion is not None:
        _validate_criterion(criterion)

    client = client or get_client()
    params: dict[str, Any] = {"uid": user_id}
    where = "user_id = {uid:String} AND deleted = 0"
    if criterion is not None:
        where += " AND criterion = {crit:String}"
        params["crit"] = criterion
    sql = (
        f"SELECT {_SELECT_COLS} FROM o1_evidence FINAL "
        f"WHERE {where} ORDER BY declared_at DESC"
    )
    result = client.query(sql, parameters=params)
    return [_row_to_item(r) for r in result.result_rows]


def evidence_by_criterion(
    user_id: str,
    client: Client | None = None,
) -> dict[str, list[EvidenceItem]]:
    """Group user's evidence by criterion.

    Returns a dict keyed by ALL eight criterion keys (empty list values
    for unused criteria), preserving the canonical USCIS_O1A_CRITERIA
    ordering.
    """
    rows = list_evidence(user_id, client=client)
    grouped: dict[str, list[EvidenceItem]] = {k: [] for k, _ in USCIS_O1A_CRITERIA}
    for item in rows:
        if item.criterion in grouped:
            grouped[item.criterion].append(item)
    return grouped


def count_satisfied_criteria(
    user_id: str,
    client: Client | None = None,
) -> int:
    """Number of distinct criteria with at least one non-deleted item.

    Returns 0..8. Executed as one SQL query against the FINAL view.
    """
    if not user_id:
        raise ValueError("user_id is required")
    client = client or get_client()
    sql = (
        "SELECT count(DISTINCT criterion) FROM o1_evidence FINAL "
        "WHERE user_id = {uid:String} AND deleted = 0"
    )
    result = client.query(sql, parameters={"uid": user_id})
    if not result.result_rows:
        return 0
    return int(result.result_rows[0][0])
