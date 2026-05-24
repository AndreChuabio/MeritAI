"""O-1A filing-readiness PDF dossier builder.

Bundles the user's declared evidence (one section per USCIS O-1A criterion)
together with freshly drafted per-criterion narratives into a single PDF an
immigration attorney can use as a starting point for an I-129 / I-140 filing.

This module owns rendering only. Evidence retrieval lives in
``paperpilot.outreach.evidence`` and narrative drafting lives in
``paperpilot.outreach.evidence_draft`` (sibling agents).

The PDF is generated in-memory via reportlab.platypus so Railway's runtime
needs no system font or LaTeX dependencies.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from paperpilot.outreach.evidence import (
    USCIS_O1A_CRITERIA,
    EvidenceItem,
    count_satisfied_criteria,
    evidence_by_criterion,
)
from paperpilot.outreach.evidence_draft import draft_all_narratives
from paperpilot.outreach import log as outreach_log

logger = logging.getLogger(__name__)


_DISCLAIMER = (
    "This document is a structured draft. It is not legal advice. "
    "Review with a qualified immigration attorney before filing."
)

_SUMMARY_NOTE = (
    "Standard O-1A petition requires evidence in at least 3 of 8 criteria. "
    "EB-1A requires 3 of 10 (different schema)."
)

_FOOTER_TEXT = "Draft -- not yet attorney-reviewed"


def _safe_html(text: str) -> str:
    """Escape characters reportlab Paragraph would interpret as markup."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _slugify_name(name: str) -> str:
    """Reduce a display name to filename-safe ASCII alphanumerics."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return cleaned or "user"


def _lookup_profile_display_name(user_id: str) -> Optional[str]:
    """Best-effort profile lookup; never raises.

    Prefers ``find_user_profile_by_id`` if a future log module exposes it;
    falls back to ``None`` if no such helper exists or the lookup throws.
    The caller decides what to display when this returns ``None``.
    """
    finder = getattr(outreach_log, "find_user_profile_by_id", None)
    if finder is None:
        return None
    try:
        profile = finder(user_id)
    except Exception:  # noqa: BLE001 -- profile lookup is best-effort
        logger.warning("profile lookup failed for user_id=%s", user_id, exc_info=True)
        return None
    if profile is None:
        return None
    return getattr(profile, "name", None) or None


def _lookup_profile_title(user_id: str) -> Optional[str]:
    """Best-effort title lookup mirroring ``_lookup_profile_display_name``."""
    finder = getattr(outreach_log, "find_user_profile_by_id", None)
    if finder is None:
        return None
    try:
        profile = finder(user_id)
    except Exception:  # noqa: BLE001 -- profile lookup is best-effort
        return None
    if profile is None:
        return None
    return getattr(profile, "title", None) or None


def _make_styles() -> dict[str, ParagraphStyle]:
    """Return the named paragraph styles used by the dossier."""
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            alignment=1,  # center
            spaceAfter=18,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            alignment=1,
            textColor=colors.HexColor("#444444"),
            spaceAfter=12,
        ),
        "cover_name": ParagraphStyle(
            "CoverName",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            alignment=1,
            spaceAfter=8,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=14,
            alignment=1,
            spaceAfter=24,
        ),
        "disclaimer": ParagraphStyle(
            "Disclaimer",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10,
            leading=13,
            alignment=1,
            textColor=colors.HexColor("#666666"),
            spaceAfter=4,
        ),
        "section_header": ParagraphStyle(
            "SectionHeader",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            spaceBefore=14,
            spaceAfter=6,
            textColor=colors.HexColor("#222222"),
        ),
        "subheader": ParagraphStyle(
            "SubHeader",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": body,
        "muted": ParagraphStyle(
            "Muted",
            parent=body,
            fontSize=10,
            textColor=colors.HexColor("#555555"),
        ),
        "item_meta": ParagraphStyle(
            "ItemMeta",
            parent=body,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#444444"),
            spaceAfter=2,
        ),
    }


def _format_evidence_date(d: Optional[date]) -> str:
    """Render an evidence date as ISO string, or empty if missing."""
    if d is None:
        return ""
    return d.isoformat()


def _criterion_label(criterion_key: str) -> str:
    """Return the human-readable label for a criterion key."""
    for key, label in USCIS_O1A_CRITERIA:
        if key == criterion_key:
            return label
    return criterion_key


def _build_item_flowable(item: EvidenceItem, styles: dict[str, ParagraphStyle]) -> list:
    """Render one declared item as a bullet point with meta lines."""
    title = _safe_html(item.title) or "(untitled)"
    parts: list = [Paragraph(f"<b>{title}</b>", styles["body"])]

    meta_lines: list[str] = []
    date_str = _format_evidence_date(item.evidence_date)
    if date_str:
        meta_lines.append(f"Date: {date_str}")
    if item.evidence_url:
        url = _safe_html(item.evidence_url)
        meta_lines.append(f'URL: <link href="{url}" color="#1a5fbf">{url}</link>')
    for line in meta_lines:
        parts.append(Paragraph(line, styles["item_meta"]))

    if item.description:
        parts.append(Paragraph(_safe_html(item.description), styles["body"]))

    return parts


def _on_page(canvas, doc) -> None:  # noqa: ANN001 -- reportlab callback signature
    """Draw the page-number plus draft watermark footer on every page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#777777"))
    page_num = canvas.getPageNumber()
    footer = f"Page {page_num}   |   {_FOOTER_TEXT}"
    canvas.drawCentredString(LETTER[0] / 2.0, 0.5 * inch, footer)
    canvas.restoreState()


def _cover_flowables(
    user_id: str,
    display_name: str,
    title_line: Optional[str],
    styles: dict[str, ParagraphStyle],
    today: date,
) -> list:
    """Build the cover-page flowables."""
    flow: list = [
        Spacer(1, 1.4 * inch),
        Paragraph(
            "O-1A Extraordinary Ability Petition &mdash; Evidence Dossier",
            styles["cover_title"],
        ),
        Paragraph(
            f"Draft prepared {today.isoformat()}. For attorney review.",
            styles["cover_subtitle"],
        ),
        Spacer(1, 0.4 * inch),
        Paragraph(_safe_html(display_name), styles["cover_name"]),
    ]
    if title_line:
        flow.append(Paragraph(_safe_html(title_line), styles["cover_meta"]))
    else:
        flow.append(Paragraph(f"user_id: {_safe_html(user_id)}", styles["cover_meta"]))

    flow.extend(
        [
            Spacer(1, 0.8 * inch),
            Paragraph(_DISCLAIMER, styles["disclaimer"]),
            PageBreak(),
        ]
    )
    return flow


def _summary_flowables(
    satisfied: int,
    styles: dict[str, ParagraphStyle],
) -> list:
    """Build the summary section that follows the cover page."""
    return [
        Paragraph("Summary", styles["section_header"]),
        Paragraph(
            f"Criteria satisfied: <b>{satisfied}</b> of 8",
            styles["body"],
        ),
        Paragraph(_SUMMARY_NOTE, styles["muted"]),
        Spacer(1, 0.2 * inch),
    ]


def _criterion_section_flowables(
    index: int,
    key: str,
    label: str,
    items: list[EvidenceItem],
    narrative: str,
    styles: dict[str, ParagraphStyle],
) -> list:
    """Build flowables for one criterion section."""
    header = f"{index}. {_safe_html(label)}"
    flow: list = [
        Paragraph(header, styles["section_header"]),
        Paragraph(f"{len(items)} item(s) declared", styles["muted"]),
    ]

    if items and narrative:
        flow.append(Paragraph("Narrative", styles["subheader"]))
        # Split narrative into paragraphs so reportlab wraps cleanly.
        for chunk in [p.strip() for p in narrative.split("\n\n") if p.strip()]:
            flow.append(Paragraph(_safe_html(chunk), styles["body"]))

    if items:
        flow.append(Paragraph("Declared evidence", styles["subheader"]))
        list_items: list[ListItem] = []
        for item in items:
            list_items.append(
                ListItem(
                    _build_item_flowable(item, styles),
                    leftIndent=12,
                    spaceBefore=4,
                    spaceAfter=4,
                )
            )
        flow.append(
            ListFlowable(
                list_items,
                bulletType="bullet",
                start="circle",
                leftIndent=18,
            )
        )
    else:
        flow.append(
            Paragraph("No evidence declared for this criterion.", styles["body"])
        )

    flow.append(Spacer(1, 0.15 * inch))
    return flow


def build_dossier(user_id: str) -> bytes:
    """Generate the O-1A dossier PDF for a user.

    Loads the user's declared evidence via
    ``paperpilot.outreach.evidence.evidence_by_criterion(user_id)``, drafts
    fresh per-criterion narratives via
    ``paperpilot.outreach.evidence_draft.draft_all_narratives(user_id)``, and
    renders the combined result as a single Letter-size PDF using reportlab.

    Returns the PDF bytes. Caller passes the result to ``st.download_button``.

    Raises:
        RuntimeError: if PDF generation itself fails (reportlab exception)
            or if narrative drafting raises. Both errors bubble up so the
            UI can surface them; no partial / empty bytes are returned.
    """
    if not user_id:
        raise ValueError("user_id is required")

    # Narrative drafting first -- if it fails, we want to fail loudly before
    # spending time rendering. Bubble the original exception via __cause__.
    try:
        narratives = draft_all_narratives(user_id)
    except Exception as exc:  # noqa: BLE001 -- escalate per contract
        raise RuntimeError(
            f"failed to draft O-1A narratives for user_id={user_id!r}"
        ) from exc

    try:
        grouped = evidence_by_criterion(user_id)
        satisfied = count_satisfied_criteria(user_id)
        display_name = _lookup_profile_display_name(user_id) or user_id
        title_line = _lookup_profile_title(user_id)

        styles = _make_styles()
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
        story.extend(_cover_flowables(user_id, display_name, title_line, styles, today))
        story.extend(_summary_flowables(satisfied, styles))

        for idx, (key, label) in enumerate(USCIS_O1A_CRITERIA, start=1):
            items = grouped.get(key, [])
            narrative = ""
            if isinstance(narratives, dict):
                narrative = (narratives.get(key) or "").strip()
            story.extend(
                _criterion_section_flowables(idx, key, label, items, narrative, styles)
            )

        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
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


def dossier_filename(user_id: str, user_name: Optional[str] = None) -> str:
    """Return a download filename like ``O1A_Dossier_{Name}_{YYYYMMDD}.pdf``.

    The name slug strips to ASCII alphanumerics; falls back to the user_id
    when ``user_name`` is missing or empty. Used by the Streamlit UI as the
    ``file_name`` kwarg on ``st.download_button``.
    """
    if not user_id:
        raise ValueError("user_id is required")
    base = user_name if user_name else user_id
    slug = _slugify_name(base)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    return f"O1A_Dossier_{slug}_{stamp}.pdf"
