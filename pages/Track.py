"""Track - O-1A visa progress with user-declared evidence ledger.

Two tabs:

- Dashboard: auto-derived heuristic gauges, tiles, and charts
  (Scholar + Senso + outreach signals).
- Evidence Ledger: user declares concrete O-1A evidence per criterion.
  The headline "X of 8" metric is driven by the ledger, not the heuristic.
"""

from __future__ import annotations

import os
from typing import Dict, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from paperpilot import ui
from paperpilot.auth import require_auth
from paperpilot.outreach import log as outreach_log
from paperpilot.outreach.scholar import O1_THRESHOLD, fetch as fetch_scholar
from paperpilot.outreach.senso import Senso, SensoAPIError

try:
    from paperpilot.outreach.evidence import (
        USCIS_O1A_CRITERIA,
        EvidenceItem,
        count_satisfied_criteria,
        declare_evidence,
        delete_evidence,
        evidence_by_criterion,
    )
    _EVIDENCE_IMPORT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001 - module may not exist yet during parallel build
    USCIS_O1A_CRITERIA = []  # type: ignore[assignment]
    EvidenceItem = None  # type: ignore[assignment,misc]
    count_satisfied_criteria = None  # type: ignore[assignment]
    declare_evidence = None  # type: ignore[assignment]
    delete_evidence = None  # type: ignore[assignment]
    evidence_by_criterion = None  # type: ignore[assignment]
    _EVIDENCE_IMPORT_ERROR = str(exc)


load_dotenv()

st.set_page_config(page_title="Track - Visa Progress", page_icon="🛂", layout="wide")

user_id = require_auth()

ui.inject_global_css()

with st.sidebar:
    ui.sidebar_brand("PaperPilot")

st.title("Track")
st.caption("Evidence-based progress toward an O-1A extraordinary-ability visa.")
st.caption(f"Logged in as {st.session_state.get('user_name', user_id)}")

_HAS_SENSO_KEY = bool(os.environ.get("SENSO_API_KEY"))


# =========================================================================
# Evidence ledger lookups (top-level, single query per page load)
# =========================================================================
satisfied: int = 0
by_criterion: Dict[str, List] = {}
_LEDGER_ERROR: str | None = None

if _EVIDENCE_IMPORT_ERROR is not None:
    _LEDGER_ERROR = f"Evidence module unavailable: {_EVIDENCE_IMPORT_ERROR}"
else:
    try:
        satisfied = count_satisfied_criteria(user_id)
        by_criterion = evidence_by_criterion(user_id)
    except Exception as exc:  # noqa: BLE001
        _LEDGER_ERROR = f"Evidence ledger unavailable: {exc}"
        satisfied = 0
        by_criterion = {key: [] for key, _ in USCIS_O1A_CRITERIA}

if _LEDGER_ERROR:
    st.error(_LEDGER_ERROR)


# =========================================================================
# Headline metric - "X of 8" + status pills (visible above tabs)
# =========================================================================
hcol1, hcol2 = st.columns([1, 2])
with hcol1:
    st.metric(
        "O-1A criteria satisfied",
        f"{satisfied} of 8",
        help="USCIS requires evidence in at least 3 of 8 criteria to qualify.",
    )
    st.caption("Threshold to qualify: 3 of 8.")

with hcol2:
    if USCIS_O1A_CRITERIA:
        pill_cols = st.columns(len(USCIS_O1A_CRITERIA))
        for i, (key, label) in enumerate(USCIS_O1A_CRITERIA):
            count = len(by_criterion.get(key, []))
            color = "#22c55e" if count >= 1 else "#6b7280"
            short_label = label.split()[0]
            pill_cols[i].markdown(
                f"<div style='text-align:center;padding:6px 6px;border-radius:8px;"
                f"background:{color}22;border:1px solid {color};"
                f"font-size:0.78rem;line-height:1.1'>"
                f"<div style='font-weight:700;color:{color};font-size:1.0rem'>{count}</div>"
                f"<div style='color:#9ca3af;margin-top:2px'>{short_label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("Criteria list unavailable - check evidence module deploy.")

st.divider()


# =========================================================================
# Data fetch for Dashboard (heuristics)
# =========================================================================
scholar_url_for_fetch = st.session_state.get("brand_scholar") or None
scholar = fetch_scholar(scholar_url_for_fetch)

try:
    posted_count = outreach_log.count_posted(user_id)
    total_drafts = outreach_log.total_drafts(user_id)
    by_channel = outreach_log.count_by_channel(user_id)
    by_purpose = outreach_log.count_by_purpose(user_id)
    by_day = outreach_log.drafts_by_day(user_id)
except Exception:
    posted_count = 0
    total_drafts = 0
    by_channel = {}
    by_purpose = {}
    by_day = []

senso_owned_total = 0
senso_external_total = 0
if _HAS_SENSO_KEY:
    try:
        s = Senso.from_env()
        senso_owned_total = s.citation_trends("owned").get("total", 0)
        senso_external_total = s.citation_trends("external").get("total", 0)
    except SensoAPIError:
        pass

papers_count = len(scholar.papers)
speaking_count = by_channel.get("email_speaker_pitch", 0)
collab_count = by_channel.get("email_collaboration", 0)
linkedin_count = (
    by_channel.get("linkedin_post_brand", 0)
    + by_channel.get("linkedin_dm", 0)
)
x_count = by_channel.get("x_thread_brand", 0)
service_count = by_channel.get("email_service", 0)
visa_drafts = by_purpose.get("VISA", 0)


def _saturate(n: float, ceil: float) -> float:
    """Clamp ratio n/ceil into [0, 1]."""
    return min(n / ceil, 1.0)


o1_score = 100 * (
    0.30 * _saturate(scholar.total_citations, O1_THRESHOLD)
    + 0.20 * _saturate(papers_count, 5)
    + 0.15 * _saturate(speaking_count + collab_count, 6)
    + 0.15 * _saturate(senso_owned_total + senso_external_total, 100)
    + 0.10 * _saturate(linkedin_count + x_count, 10)
    + 0.10 * _saturate(posted_count, 10)
)

niw_score = 100 * (
    0.40 * _saturate(scholar.total_citations, O1_THRESHOLD)
    + 0.25 * _saturate(papers_count, 5)
    + 0.20 * _saturate(speaking_count + collab_count + linkedin_count, 10)
    + 0.15 * _saturate(total_drafts, 20)
)


def _readiness_block(label: str, score: float, caption: str) -> None:
    """Render a compact readiness gauge - number + bar + caption.

    Demoted from the prior large-card treatment because these are heuristic,
    not USCIS-official. The authoritative count lives in the Evidence Ledger.
    """
    st.markdown(
        f'<div class="pp-card" style="padding: 14px 16px;">'
        f'<div style="display:flex; align-items:baseline; justify-content:space-between;">'
        f'<div style="color: var(--fg-muted); font-size: 0.72rem; '
        f'font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;">'
        f'{label}'
        f'</div>'
        f'<div style="color: var(--fg-dim); font-family: var(--font-mono); '
        f'font-size: 0.72rem;">/ 100</div>'
        f'</div>'
        f'<div style="font-size: 1.9rem; font-weight: 800; color: var(--fg); '
        f'line-height: 1.1; letter-spacing: -0.02em; margin: 4px 0 8px 0;">'
        f'{score:.0f}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.progress(min(max(score / 100, 0.0), 1.0))
    st.caption(caption)


# =========================================================================
# Tabs
# =========================================================================
tabs = st.tabs(["Dashboard", "Evidence Ledger"])


# -------------------------------------------------------------------------
# Tab 1: Dashboard (existing content, gauges demoted)
# -------------------------------------------------------------------------
with tabs[0]:
    st.caption(
        "Auto-derived heuristics from Scholar, Senso, and outreach data. "
        "Not USCIS-official - declare evidence in the Ledger tab for the real count."
    )

    col_o1, col_niw = st.columns(2)
    with col_o1:
        _readiness_block(
            "O-1 Heuristic",
            o1_score,
            "Auto-derived heuristic - not USCIS-official.",
        )
    with col_niw:
        _readiness_block(
            "NIW Heuristic",
            niw_score,
            "Auto-derived heuristic - not USCIS-official.",
        )

    st.divider()

    st.subheader("Evidence by category")
    st.caption(
        "Each tile maps to a USCIS evidence criterion you can cite in your petition."
    )

    _TILES = [
        ("📄", "Research papers", str(papers_count),
         "Authored scholarly articles (Google Scholar)."),
        ("📈", "Academic citations", f"{scholar.total_citations} / {O1_THRESHOLD}",
         "Twenty citations is the widely-cited O-1 threshold for original contributions."),
        ("🤖", "AI citations (Senso)", str(senso_owned_total + senso_external_total),
         "How often ChatGPT, Perplexity, Claude cite your work. Published material about."),
        ("📊", "h-index", str(scholar.h_index),
         "From Google Scholar."),
        ("🎤", "Speaker pitches", str(speaking_count),
         "Conference-organizer pitches drafted (judging / critical role evidence)."),
        ("🤝", "Collaboration outreach", str(collab_count),
         "Academic collaboration emails drafted."),
        ("💼", "LinkedIn activity", str(linkedin_count),
         "LinkedIn posts + DMs drafted (network reach + published material)."),
        ("🐦", "X / Twitter threads", str(x_count),
         "Public threads drafted (published material about you)."),
        ("📨", "Service outreach", str(service_count),
         "Service / product emails drafted."),
        ("📦", "Total drafts", str(total_drafts),
         "All drafts across all channels."),
        ("✅", "Posted (shipped)", str(posted_count),
         "Drafts that hit Post."),
        ("🛂", "VISA-purpose drafts", str(visa_drafts),
         "Drafts explicitly tagged with the VISA purpose."),
    ]

    for row_start in range(0, len(_TILES), 4):
        row = _TILES[row_start:row_start + 4]
        cols = st.columns(4)
        for col, (icon, label, value, hint) in zip(cols, row):
            with col:
                ui.evidence_tile(icon, label, value, hint=hint)

    st.divider()

    col_chart, col_time = st.columns(2)
    with col_chart:
        st.subheader("Per-channel breakdown")
        if by_channel:
            df = pd.DataFrame(
                [{"channel": k, "drafts": v} for k, v in by_channel.items()]
            )
            st.bar_chart(df, x="channel", y="drafts", height=280)
        else:
            st.caption("No drafts yet - generate some from the Market page.")

    with col_time:
        st.subheader("Drafts over time")
        if by_day:
            df = pd.DataFrame(by_day)
            st.line_chart(df, x="date", y="count", height=280)
        else:
            st.caption(
                "Timeline appears once you've generated drafts across multiple days."
            )

    st.divider()

    st.subheader("Citation trajectory")
    if scholar.by_month:
        df = pd.DataFrame(scholar.by_month)
        st.line_chart(df, x="date", y="count", height=240)
    st.caption(
        f"Currently {scholar.total_citations} / {O1_THRESHOLD} academic citations. "
        ">=20 is widely cited as the bar for the O-1 original-contributions prong."
    )


# -------------------------------------------------------------------------
# Tab 2: Evidence Ledger (user-declared per criterion)
# -------------------------------------------------------------------------
with tabs[1]:
    st.caption(
        "Declare concrete evidence for each USCIS O-1A criterion. "
        "Each declared item counts toward the headline metric above. "
        "USCIS requires evidence in at least 3 of 8 criteria."
    )

    if _EVIDENCE_IMPORT_ERROR is not None:
        st.error(
            "Evidence ledger module not deployed yet. "
            "Once paperpilot.outreach.evidence ships, this tab activates automatically."
        )
    elif not USCIS_O1A_CRITERIA:
        st.warning("No criteria configured - check the evidence module.")
    else:
        for idx, (key, label) in enumerate(USCIS_O1A_CRITERIA):
            items = by_criterion.get(key, [])
            n = len(items)
            if n >= 1:
                count_marker = f"**{n} item(s) declared**"
            else:
                count_marker = "0 items declared"
            expander_label = f"{idx + 1}. {label}  -  {count_marker}"

            with st.expander(expander_label, expanded=(n == 0 and idx < 3)):
                # Render declared items
                if items:
                    for item in items:
                        item_id = getattr(item, "id", "")
                        title = getattr(item, "title", "") or "(untitled)"
                        description = getattr(item, "description", "") or ""
                        evidence_url = getattr(item, "evidence_url", "") or ""
                        evidence_date = getattr(item, "evidence_date", None)

                        row_l, row_r = st.columns([5, 1])
                        with row_l:
                            st.markdown(f"**{title}**")
                            if description:
                                st.caption(description)
                            meta_bits: List[str] = []
                            if evidence_date:
                                meta_bits.append(str(evidence_date))
                            if evidence_url:
                                meta_bits.append(f"[link]({evidence_url})")
                            if meta_bits:
                                st.markdown(
                                    " - ".join(meta_bits),
                                    unsafe_allow_html=False,
                                )
                        with row_r:
                            if st.button(
                                "Delete",
                                key=f"delete_{item_id}",
                                use_container_width=True,
                            ):
                                try:
                                    delete_evidence(user_id, item_id)
                                    st.success("Deleted.")
                                    st.rerun()
                                except Exception as exc:  # noqa: BLE001
                                    st.error(f"Delete failed: {exc}")
                        st.markdown(
                            "<div style='height:1px;background:#1f2937;margin:6px 0'></div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption(
                        "No evidence declared yet for this criterion. "
                        "Add your first item below."
                    )

                # Add-evidence form
                show_form_key = f"show_form_{key}"
                if show_form_key not in st.session_state:
                    st.session_state[show_form_key] = False

                if not st.session_state[show_form_key]:
                    if st.button(
                        "+ Add evidence",
                        key=f"toggle_add_{key}",
                    ):
                        st.session_state[show_form_key] = True
                        st.rerun()
                else:
                    with st.form(key=f"declare_form_{key}", clear_on_submit=True):
                        title_val = st.text_input(
                            "Title",
                            key=f"title_{key}",
                            placeholder="Short headline of the evidence",
                        )
                        description_val = st.text_area(
                            "Description",
                            key=f"description_{key}",
                            help="What did you do, when, why does it matter?",
                            placeholder="Concise narrative for the petition.",
                        )
                        url_val = st.text_input(
                            "Evidence URL (optional)",
                            key=f"url_{key}",
                            placeholder="https://...",
                        )
                        date_val = st.date_input(
                            "Evidence date (optional)",
                            key=f"date_{key}",
                            value=None,
                        )

                        submit_col, cancel_col = st.columns([1, 1])
                        with submit_col:
                            submitted = st.form_submit_button(
                                "Declare",
                                use_container_width=True,
                            )
                        with cancel_col:
                            cancelled = st.form_submit_button(
                                "Cancel",
                                use_container_width=True,
                            )

                        if cancelled:
                            st.session_state[show_form_key] = False
                            st.rerun()

                        if submitted:
                            if not title_val.strip() or not description_val.strip():
                                st.error("Title and description are required.")
                            else:
                                try:
                                    declare_evidence(
                                        user_id,
                                        key,
                                        title_val.strip(),
                                        description_val.strip(),
                                        evidence_url=url_val.strip(),
                                        evidence_date=date_val,
                                    )
                                    st.session_state[show_form_key] = False
                                    st.success("Declared.")
                                    st.rerun()
                                except Exception as exc:  # noqa: BLE001
                                    st.error(f"Declare failed: {exc}")
