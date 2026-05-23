"""Outreach workflow — Streamlit multipage entry.

Auto-discovered by Streamlit when `streamlit run app.py` finds this file
under `pages/`. Does NOT modify `app.py` — kept isolated so main-branch
work on the PaperPilot pipeline does not merge-conflict here.

Three internal sub-tabs:
  1. Brand   — sync Senso Brand Kit + mirror to ClickHouse user_profile
  2. Outreach — purpose picker -> Senso content generation -> draft cards
  3. Track   — Scholar (Nimble live or mock) + Senso citations + drafts
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from paperpilot import trace
from paperpilot.outreach import log as outreach_log
from paperpilot.outreach.log import UserProfile, upsert_user_profile
from paperpilot.outreach.orchestrator import generate_drafts
from paperpilot.outreach.purpose import Purpose
from paperpilot.outreach.scholar import O1_THRESHOLD, fetch as fetch_scholar
from paperpilot.outreach.senso import Senso, SensoAPIError


load_dotenv()


st.set_page_config(page_title="Outreach — PaperPilot", page_icon="📣", layout="wide")
st.title("📣 Outreach")
st.caption(
    "Senso-backed brand sync, purpose-driven drafts, and a visa-progress dashboard. "
    "Drafts powered by **Senso** · Scholar live-fetch via **Nimble**."
)


_HAS_SENSO_KEY = bool(os.environ.get("SENSO_API_KEY"))
if not _HAS_SENSO_KEY:
    st.warning(
        "`SENSO_API_KEY` not set. Brand sync + draft generation are disabled. "
        "Add the key to `.env` and restart to enable Senso flows."
    )


tab_brand, tab_outreach, tab_track = st.tabs(["Brand", "Outreach", "Track"])


# =========================================================================
# Brand tab — Senso Brand Kit + ClickHouse mirror
# =========================================================================
with tab_brand:
    st.subheader("Your Brand on Senso")
    st.caption("Synced to workspace **Agentic-hack** at apiv2.senso.ai")

    col_l, col_r = st.columns(2)
    name = col_l.text_input("Name", value=st.session_state.get("brand_name", ""))
    title = col_r.text_input("Title", value=st.session_state.get("brand_title", ""))
    about = st.text_area(
        "About",
        value=st.session_state.get("brand_about", ""),
        placeholder="3-5 sentences. Who you are, what you work on, who you help.",
        height=120,
    )
    voice = st.text_area(
        "Voice & tone",
        value=st.session_state.get("brand_voice", ""),
        placeholder="e.g. warm, evidence-based, jargon-free — like a clinician explaining to a peer.",
        height=80,
    )

    st.markdown("**Links**")
    c1, c2 = st.columns(2)
    github_url   = c1.text_input("GitHub",   value=st.session_state.get("brand_github", ""))
    linkedin_url = c2.text_input("LinkedIn", value=st.session_state.get("brand_linkedin", ""))
    c3, c4 = st.columns(2)
    scholar_url  = c3.text_input("Google Scholar", value=st.session_state.get("brand_scholar", ""))
    site_url     = c4.text_input("Site",     value=st.session_state.get("brand_site", ""))

    resume_text = st.text_area(
        "Resume (paste contents)",
        value=st.session_state.get("brand_resume", ""),
        height=160,
    )

    col_sync, col_load = st.columns([1, 1])
    if col_sync.button("Sync to Senso", type="primary", disabled=not _HAS_SENSO_KEY):
        payload = {
            "brand_name": name,
            "brand_description": f"{about}\n\n{resume_text}".strip(),
            "voice_and_tone": voice,
            "guidelines": {
                "title": title,
                "links": {
                    "github":   github_url,
                    "linkedin": linkedin_url,
                    "scholar":  scholar_url,
                    "site":     site_url,
                },
            },
        }
        try:
            Senso.from_env().put_brand_kit(payload)
            st.success("Synced to Senso ✓")
        except SensoAPIError as e:
            st.error(f"Senso error: {e}")

        # Mirror into ClickHouse user_profile (best-effort).
        try:
            upsert_user_profile(UserProfile(
                user_id="demo",
                name=name, title=title, about=about, voice_tone=voice,
                github_url=github_url, linkedin_url=linkedin_url,
                scholar_url=scholar_url, site_url=site_url,
                resume_text=resume_text,
            ))
        except Exception as e:  # noqa: BLE001
            st.caption(f"(ClickHouse mirror skipped: {e})")

        # Persist into session_state so tab switches do not clear the form.
        st.session_state["brand_name"] = name
        st.session_state["brand_title"] = title
        st.session_state["brand_about"] = about
        st.session_state["brand_voice"] = voice
        st.session_state["brand_github"] = github_url
        st.session_state["brand_linkedin"] = linkedin_url
        st.session_state["brand_scholar"] = scholar_url
        st.session_state["brand_site"] = site_url
        st.session_state["brand_resume"] = resume_text

    if col_load.button("Load current from Senso", disabled=not _HAS_SENSO_KEY):
        try:
            kit = Senso.from_env().get_brand_kit()
            st.json(kit)
        except SensoAPIError as e:
            st.error(f"Senso error: {e}")


# =========================================================================
# Outreach tab — purpose -> Senso drafts
# =========================================================================
with tab_outreach:
    st.subheader("Outreach Drafts")
    st.caption("Pick a purpose; Senso writes the cards.")

    purpose_label = st.radio(
        "Purpose",
        options=[p.value for p in Purpose],
        horizontal=True,
        captions=[
            "Extraordinary-ability dossier (O-1)",
            "Networking / mentorship",
            "Personal brand building",
            "Sell a service or product",
        ],
    )
    user_ctx = st.text_area(
        "What's this about?",
        placeholder="e.g. I want to apply to keynote at ML4H 2026 on retrieval calibration for medical QA.",
        height=100,
    )

    if st.button(
        "Generate",
        type="primary",
        disabled=(not _HAS_SENSO_KEY) or (not user_ctx.strip()),
    ):
        sid = st.session_state.get("outreach_sid") or trace.new_session()
        st.session_state["outreach_sid"] = sid
        with st.spinner("Drafting via Senso..."):
            cards = generate_drafts(
                senso=Senso.from_env(),
                purpose=purpose_label,
                context=user_ctx,
                session_id=sid,
                logger=outreach_log,
            )
        st.session_state["outreach_cards"] = cards

    cards = st.session_state.get("outreach_cards", [])
    for i, card in enumerate(cards):
        st.markdown(f"### {card.channel}")
        if card.error:
            st.error(f"Generation failed: {card.error}")
            continue
        st.text_area(
            "Draft",
            value=card.markdown,
            key=f"draft_{i}_{card.sample_job_id}",
            height=240,
        )
        c1, c2 = st.columns([1, 1])
        if c1.button("Copy", key=f"copy_{i}"):
            st.toast("Copied to clipboard (demo)")
        if c2.button(f"Post to {card.channel.split('_')[0]}", key=f"post_{i}"):
            try:
                outreach_log.mark_posted(
                    sample_job_id=card.sample_job_id,
                    draft_id=card.draft_id,
                )
            except Exception:
                pass  # CH mirror is best-effort
            st.toast(f"Posted to {card.channel} ✓ (demo)")


# =========================================================================
# Track tab — Scholar + Senso citations + composite score
# =========================================================================
with tab_track:
    st.subheader("Visa Progress Dashboard")

    scholar_url_for_fetch = st.session_state.get("brand_scholar") or None
    scholar = fetch_scholar(scholar_url_for_fetch)

    try:
        posted = outreach_log.count_posted("demo")
    except Exception:
        posted = 0

    senso_owned_total = 0
    senso_external_total = 0
    drafts: list[dict] = []
    if _HAS_SENSO_KEY:
        try:
            s = Senso.from_env()
            senso_owned_total = s.citation_trends("owned").get("total", 0)
            senso_external_total = s.citation_trends("external").get("total", 0)
            drafts = s.list_drafts(limit=5)
        except SensoAPIError:
            pass

    score = (
        0.4 * min(scholar.total_citations / O1_THRESHOLD, 1.0)
        + 0.3 * min((senso_owned_total + senso_external_total) / 100.0, 1.0)
        + 0.3 * min(posted / 25.0, 1.0)
    ) * 100

    st.metric("Extraordinary Ability score", f"{score:.0f} / 100")
    st.progress(score / 100)

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("**Academic citations (Scholar)**")
        st.metric(
            f"{scholar.total_citations} / {O1_THRESHOLD}",
            f"h-index {scholar.h_index}",
        )
        st.progress(scholar.progress_to_o1())
        if scholar.by_month:
            df = pd.DataFrame(scholar.by_month)
            st.line_chart(df, x="date", y="count", height=160)
        st.caption("≥20 citations is widely cited as the O-1 threshold.")

    with col_b:
        st.markdown("**AI citations (Senso)**")
        st.metric("Owned", senso_owned_total)
        st.metric("External", senso_external_total)
        st.caption("How often ChatGPT, Perplexity, Claude cite your work.")

    with col_c:
        st.markdown("**Drafts published**")
        st.metric("This workspace", posted)
        for d in drafts:
            title = (d.get("seo_title") or d.get("raw_markdown") or d.get("id", ""))
            st.write(f"- {str(title)[:80]}")
        if not drafts and _HAS_SENSO_KEY:
            st.caption("No drafts yet — generate one from the Outreach tab.")
