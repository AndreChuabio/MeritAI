"""Track — O-1 + National Interest Waiver progress dashboard.

Separate Streamlit sidebar page. Aggregates every signal we have about
the candidate's readiness for an O-1 (extraordinary ability) and NIW
(national interest waiver) case:

- Authored scholarly articles (Google Scholar)
- Citations & impact (Scholar academic + Senso AI)
- Speaking + collaboration outreach drafted (outreach_log)
- LinkedIn / X social-brand activity (outreach_log)
- Posted-vs-drafted conversion

Two headline gauges (O-1, NIW) summarize evidence categories aligned to
the USCIS criteria sets. Per-channel bar chart + drafts-over-time line.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from paperpilot.outreach import log as outreach_log
from paperpilot.outreach.scholar import O1_THRESHOLD, fetch as fetch_scholar
from paperpilot.outreach.senso import Senso, SensoAPIError


load_dotenv()

st.set_page_config(page_title="Track — Visa Progress", page_icon="🛂", layout="wide")

st.markdown(
    """<style>
    [data-testid="stSidebar"] {
        width: 190px !important;
        min-width: 190px !important;
        max-width: 190px !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] li {
        font-size: 0.85rem !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

st.title("🛂 Track — O-1 + NIW Progress")
st.caption(
    "Every signal we have on your case, mapped to USCIS extraordinary-ability + "
    "national-interest-waiver criteria. Refresh after generating new drafts."
)

_HAS_SENSO_KEY = bool(os.environ.get("SENSO_API_KEY"))


# =========================================================================
# Pull data
# =========================================================================
scholar_url_for_fetch = st.session_state.get("brand_scholar") or None
scholar = fetch_scholar(scholar_url_for_fetch)

try:
    posted_count = outreach_log.count_posted("demo")
    total_drafts = outreach_log.total_drafts("demo")
    by_channel = outreach_log.count_by_channel("demo")
    by_purpose = outreach_log.count_by_purpose("demo")
    by_day = outreach_log.drafts_by_day("demo")
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

# Channel buckets aligned to visa criteria.
papers_count = len(scholar.papers)
speaking_count = by_channel.get("email_speaker_pitch", 0)
collab_count = by_channel.get("email_collaboration", 0)
linkedin_count = (
    by_channel.get("linkedin_post_brand", 0)
    + by_channel.get("linkedin_dm_career", 0)
)
x_count = by_channel.get("x_thread_brand", 0)
service_count = by_channel.get("email_service", 0)
visa_drafts = by_purpose.get("VISA", 0)


# =========================================================================
# Headline gauges — O-1 + NIW readiness scores (UX-flavor formulas).
# =========================================================================
def _saturate(n: float, ceil: float) -> float:
    return min(n / ceil, 1.0)


# O-1A weights: scholarly articles (papers), original contributions (citations),
# judging (speaking pitches), published material about candidate (AI citations),
# media reach (social outreach).
o1_score = 100 * (
    0.30 * _saturate(scholar.total_citations, O1_THRESHOLD)
    + 0.20 * _saturate(papers_count, 5)
    + 0.15 * _saturate(speaking_count + collab_count, 6)
    + 0.15 * _saturate(senso_owned_total + senso_external_total, 100)
    + 0.10 * _saturate(linkedin_count + x_count, 10)
    + 0.10 * _saturate(posted_count, 10)
)

# NIW weights: substantial merit & national importance (papers + impact);
# well-positioned (publications + outreach); on-balance benefits US (volume).
niw_score = 100 * (
    0.40 * _saturate(scholar.total_citations, O1_THRESHOLD)
    + 0.25 * _saturate(papers_count, 5)
    + 0.20 * _saturate(speaking_count + collab_count + linkedin_count, 10)
    + 0.15 * _saturate(total_drafts, 20)
)

col_o1, col_niw = st.columns(2)
with col_o1:
    st.metric("O-1 Readiness", f"{o1_score:.0f} / 100")
    st.progress(o1_score / 100)
    st.caption(
        "USCIS O-1A: scholarly articles, original contributions of major "
        "significance, judging, published material, critical employment."
    )
with col_niw:
    st.metric("NIW Readiness", f"{niw_score:.0f} / 100")
    st.progress(niw_score / 100)
    st.caption(
        "EB-2 NIW: substantial-merit endeavor, national importance, "
        "well-positioned to advance the field."
    )

st.divider()


# =========================================================================
# Evidence categories — per-criterion counts
# =========================================================================
st.subheader("Evidence by category")
st.caption("Each tile maps to a USCIS evidence criterion you can cite in your petition.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("📄 Research papers", papers_count, help="Authored scholarly articles (Google Scholar).")
c2.metric(
    "📈 Academic citations",
    f"{scholar.total_citations} / {O1_THRESHOLD}",
    help="≥20 citations is the widely-cited O-1 threshold for original contributions.",
)
c3.metric(
    "🤖 AI citations (Senso)",
    senso_owned_total + senso_external_total,
    help="How often ChatGPT, Perplexity, Claude cite your work. 'Published material about'.",
)
c4.metric("h-index", scholar.h_index, help="From Google Scholar.")

c5, c6, c7, c8 = st.columns(4)
c5.metric(
    "🎤 Speaker pitches",
    speaking_count,
    help="Conference-organizer pitches drafted (judging / critical role evidence).",
)
c6.metric(
    "🤝 Collaboration outreach",
    collab_count,
    help="Academic collaboration emails drafted.",
)
c7.metric(
    "💼 LinkedIn activity",
    linkedin_count,
    help="LinkedIn posts + DMs drafted (network reach + published material).",
)
c8.metric(
    "🐦 X / Twitter threads",
    x_count,
    help="Public threads drafted (published material about you).",
)

c9, c10, c11, c12 = st.columns(4)
c9.metric("📨 Service outreach", service_count, help="Service / product emails drafted.")
c10.metric("📊 Total drafts", total_drafts, help="All drafts across all channels.")
c11.metric("✅ Posted (shipped)", posted_count, help="Drafts that hit Post.")
c12.metric(
    "🛂 VISA-purpose drafts",
    visa_drafts,
    help="Drafts explicitly tagged with the VISA purpose.",
)

st.divider()


# =========================================================================
# Channel breakdown + activity timeline
# =========================================================================
col_chart, col_time = st.columns(2)

with col_chart:
    st.subheader("Per-channel breakdown")
    if by_channel:
        df = pd.DataFrame(
            [{"channel": k, "drafts": v} for k, v in by_channel.items()]
        )
        st.bar_chart(df, x="channel", y="drafts", height=280)
    else:
        st.caption("No drafts yet — generate some from the **Market** page.")

with col_time:
    st.subheader("Drafts over time")
    if by_day:
        df = pd.DataFrame(by_day)
        st.line_chart(df, x="date", y="count", height=280)
    else:
        st.caption("Timeline appears once you've generated drafts across multiple days.")

st.divider()


# =========================================================================
# Citation timeline (Scholar mock) — keeps the climbing-to-20 visual
# =========================================================================
st.subheader("Citation trajectory")
if scholar.by_month:
    df = pd.DataFrame(scholar.by_month)
    st.line_chart(df, x="date", y="count", height=240)
st.caption(
    f"Currently {scholar.total_citations} / {O1_THRESHOLD} academic citations. "
    "≥20 is widely cited as the bar for the O-1 original-contributions prong."
)
