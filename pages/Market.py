"""Market — Senso brand sync + purpose-driven draft generation.

Separate Streamlit sidebar page. Two sub-tabs:
  1. Brand    — sync Senso Brand Kit + mirror to ClickHouse user_profile
  2. Generate — purpose picker -> Senso content generation -> draft cards

The visa-progress dashboard lives on its own `Track` page next door.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from paperpilot import trace
from paperpilot.outreach import log as outreach_log
from paperpilot.outreach.log import (
    UserProfile,
    upsert_user_profile,
    find_user_profile_by_name,
)
from paperpilot.outreach.orchestrator import generate_drafts
from paperpilot.outreach.purpose import Purpose
from paperpilot.outreach.senso import Senso, SensoAPIError


load_dotenv()


st.set_page_config(page_title="Market — Outreach Drafts", page_icon="📣", layout="wide")

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

st.title("📣 Market")
st.caption(
    "Personal-brand profile + purpose-driven outreach drafts. "
    "See your visa progress on the **Track** page."
)


_HAS_SENSO_KEY = bool(os.environ.get("SENSO_API_KEY"))
if not _HAS_SENSO_KEY:
    st.warning(
        "Profile + draft generation are disabled until the brand engine is configured. "
        "Set `SENSO_API_KEY` in `.env` and restart."
    )


tab_brand, tab_generate = st.tabs(["Personal Brand", "Generate"])


# =========================================================================
# Personal Brand tab — user-facing profile (Senso under the hood)
# =========================================================================
with tab_brand:
    # Top-right "Load My Profile" search (first + last name)
    header_l, header_r = st.columns([3, 2])
    with header_l:
        st.subheader("Build Your Profile")
        st.caption("Define your voice, story, and links. We use this to draft every outreach.")
    with header_r:
        st.markdown("**Already have a profile?**")
        load_c1, load_c2 = st.columns([3, 1])
        load_name = load_c1.text_input(
            "Name", key="load_name", label_visibility="collapsed", placeholder="Your name"
        )
        if load_c2.button("Load My Profile", disabled=not _HAS_SENSO_KEY, use_container_width=True):
            full = load_name.strip()
            if not full:
                st.warning("Enter your name.")
            else:
                try:
                    p = find_user_profile_by_name(full)
                except Exception as e:  # noqa: BLE001
                    p = None
                    st.error(f"Lookup failed: {e}")
                if p is None:
                    st.warning(f"No profile found for '{full}'.")
                else:
                    st.session_state["brand_name"] = p.name
                    st.session_state["brand_title"] = p.title
                    st.session_state["brand_about"] = p.about
                    st.session_state["brand_voice"] = p.voice_tone
                    st.session_state["brand_github"] = p.github_url
                    st.session_state["brand_linkedin"] = p.linkedin_url
                    st.session_state["brand_scholar"] = p.scholar_url
                    st.session_state["brand_site"] = p.site_url
                    st.session_state["brand_resume"] = p.resume_text
                    st.success(f"Loaded profile for {p.name} ✓")
                    st.rerun()

    col_l, col_r = st.columns(2)
    name = col_l.text_input("Name", value=st.session_state.get("brand_name", "Nikki"))
    title = col_r.text_input("Title", value=st.session_state.get("brand_title", "Software Engineer"))
    about = st.text_area(
        "About",
        value=st.session_state.get(
            "brand_about",
            "I want to work on building my career and work towards O1 visa.",
        ),
        placeholder="3-5 sentences. Who you are, what you work on, who you help.",
        height=120,
    )
    voice = st.text_area(
        "Voice & tone",
        value=st.session_state.get(
            "brand_voice",
            "professional, warm and succinct.",
        ),
        placeholder="e.g. warm, evidence-based, jargon-free — like a clinician explaining to a peer.",
        height=80,
    )

    st.markdown("**Links**")
    c1, c2 = st.columns(2)
    github_url   = c1.text_input(
        "GitHub",
        value=st.session_state.get("brand_github", "http://github.com/huhu42"),
    )
    linkedin_url = c2.text_input(
        "LinkedIn",
        value=st.session_state.get("brand_linkedin", "https://www.linkedin.com/in/nikkihu/"),
    )
    c3, c4 = st.columns(2)
    scholar_url  = c3.text_input("Google Scholar", value=st.session_state.get("brand_scholar", ""))
    site_url     = c4.text_input("Site",     value=st.session_state.get("brand_site", ""))

    resume_text = st.text_area(
        "Resume (paste contents)",
        value=st.session_state.get("brand_resume", ""),
        height=160,
    )

    if st.button("Save My Profile", type="primary", disabled=not _HAS_SENSO_KEY):
        # NOTE: Senso silently drops top-level brand_name/description/voice;
        # every field must live INSIDE `guidelines`. Links + role baked into
        # brand_description so the drafter still sees them.
        links_block = "\n".join(filter(None, [
            f"GitHub: {github_url}" if github_url else "",
            f"LinkedIn: {linkedin_url}" if linkedin_url else "",
            f"Google Scholar: {scholar_url}" if scholar_url else "",
            f"Site: {site_url}" if site_url else "",
        ]))
        description = "\n\n".join(filter(None, [
            f"Role: {title}" if title else "",
            about.strip(),
            resume_text.strip(),
            links_block,
        ]))
        rules: list[str] = [r.strip() for r in voice.replace("\n", ",").split(",") if r.strip()]
        payload = {
            "guidelines": {
                "brand_name": name,
                "brand_description": description,
                "voice_and_tone": voice,
                "author_persona": title or "",
                "global_writing_rules": rules,
            },
        }
        try:
            Senso.from_env().put_brand_kit(payload)
            st.success("Profile saved ✓")
        except SensoAPIError as e:
            st.error(f"Save failed: {e}")

        # Mirror into ClickHouse user_profile so the Load search can find it.
        user_id_slug = "_".join(name.lower().split()) or "demo"
        try:
            upsert_user_profile(UserProfile(
                user_id=user_id_slug,
                name=name, title=title, about=about, voice_tone=voice,
                github_url=github_url, linkedin_url=linkedin_url,
                scholar_url=scholar_url, site_url=site_url,
                resume_text=resume_text,
            ))
        except Exception as e:  # noqa: BLE001
            st.caption(f"(Profile-store mirror skipped: {e})")

        st.session_state["brand_name"] = name
        st.session_state["brand_title"] = title
        st.session_state["brand_about"] = about
        st.session_state["brand_voice"] = voice
        st.session_state["brand_github"] = github_url
        st.session_state["brand_linkedin"] = linkedin_url
        st.session_state["brand_scholar"] = scholar_url
        st.session_state["brand_site"] = site_url
        st.session_state["brand_resume"] = resume_text


# =========================================================================
# Generate tab — purpose -> Senso drafts
# =========================================================================
with tab_generate:
    st.subheader("Outreach Drafts")
    st.caption("Pick a purpose; Senso writes the cards.")

    purpose_label = st.radio(
        "Purpose",
        options=[p.value for p in Purpose],
        horizontal=True,
        captions=[
            "Extraordinary-ability dossier (O-1 / NIW)",
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
