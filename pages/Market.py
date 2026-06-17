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

from paperpilot import trace, ui
from paperpilot.auth import require_auth
from paperpilot.outreach import log as outreach_log
from paperpilot.outreach.log import (
    UserProfile,
    upsert_user_profile,
    find_user_profile_by_name,
)
from paperpilot.outreach.orchestrator import generate_drafts
from paperpilot.outreach.github_repos import list_user_repos
from paperpilot.outreach.nimble import NimbleClient, NimbleAPIError
from paperpilot.outreach.purpose import Purpose
from paperpilot.outreach.scholar import fetch as fetch_scholar
from paperpilot.outreach.senso import Senso, SensoAPIError


load_dotenv()


st.set_page_config(page_title="Market — Outreach Drafts", page_icon="📣", layout="wide")

user_id = require_auth()

ui.inject_global_css()

with st.sidebar:
    ui.sidebar_brand("Merit")

ui.hero(
    "Market",
    "Personal-brand profile + purpose-driven outreach drafts. "
    "See your visa progress on the Track page.",
)


_HAS_SENSO_KEY = bool(os.environ.get("SENSO_API_KEY"))
if not _HAS_SENSO_KEY:
    st.warning(
        "Profile + draft generation are disabled until the brand engine is configured. "
        "Set `SENSO_API_KEY` in `.env` and restart."
    )


_HAS_NIMBLE_KEY = bool(os.environ.get("NIMBLE_API_KEY"))

tab_brand, tab_generate, tab_search, tab_blast = st.tabs(
    ["Personal Brand", "Generate Content", "Search People", "Blast"]
)


# =========================================================================
# Personal Brand tab — user-facing profile (Senso under the hood)
# =========================================================================
with tab_brand:
    # Top-right "Load My Profile" — current user only, no search input.
    header_l, header_r = st.columns([3, 2])
    with header_l:
        st.subheader("Build Your Profile")
        st.caption("Define your voice, story, and links. We use this to draft every outreach.")
    with header_r:
        st.markdown(f"**Logged in:** {st.session_state.get('user_name', user_id)}")
        if st.button(
            "Load My Profile",
            disabled=not _HAS_SENSO_KEY,
            use_container_width=True,
            key="load_my_profile_btn",
        ):
            own_name = st.session_state.get("user_name") or user_id
            try:
                p = find_user_profile_by_name(own_name)
            except Exception as e:  # noqa: BLE001
                p = None
                st.error(f"Lookup failed: {e}")
            if p is None:
                st.warning(f"No saved profile yet for {own_name}.")
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
                st.success(f"Loaded profile for {p.name}")
                st.rerun()

    col_l, col_r = st.columns(2)
    name = col_l.text_input("Name", value=st.session_state.get("brand_name", "Nikki"))
    title = col_r.text_input("Title", value=st.session_state.get("brand_title", "Software Engineer"))
    about = st.text_area(
        "About",
        value=st.session_state.get(
            "brand_about",
            "I want to work on building my career and work towards expedited extraordinary abilities visa.",
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

        # Mirror into ClickHouse user_profile, keyed by authed user_id.
        try:
            upsert_user_profile(UserProfile(
                user_id=user_id,
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
            "Collaborate with a research lab / faculty",
            "Personal brand building",
            "Sell a service or product",
        ],
    )
    user_ctx = st.text_area(
        "What's this about?",
        value=st.session_state.get(
            "gen_user_ctx",
            "I'd like to collaborate with your research lab as a visiting scholar.",
        ),
        placeholder="e.g. I want to apply to keynote at ML4H 2026 on retrieval calibration for medical QA.",
        height=100,
        key="gen_user_ctx",
    )

    if st.button(
        "Generate",
        type="primary",
        disabled=(not _HAS_SENSO_KEY) or (not user_ctx.strip()),
    ):
        sid = st.session_state.get("outreach_sid") or trace.new_session(user_id)
        st.session_state["outreach_sid"] = sid
        with st.spinner("Drafting via Senso..."):
            cards = generate_drafts(
                senso=Senso.from_env(),
                purpose=purpose_label,
                context=user_ctx,
                session_id=sid,
                user_id=user_id,
                logger=outreach_log,
            )
        st.session_state["outreach_cards"] = cards

    cards = st.session_state.get("outreach_cards", [])
    for i, card in enumerate(cards):
        st.markdown(f"### {card.channel}")
        if card.error:
            st.error(f"Generation failed: {card.error}")
            continue
        edited = st.text_area(
            "Draft",
            value=card.markdown,
            key=f"draft_{i}_{card.sample_job_id}",
            height=240,
        )
        c1, c2 = st.columns([1, 1])
        if c1.button("Add to Blast", key=f"blast_{i}", type="secondary"):
            blast = st.session_state.setdefault("blast_queue", [])
            blast.append({
                "channel": card.channel,
                "markdown": edited or card.markdown,
                "sample_job_id": card.sample_job_id,
            })
            st.toast(f"Added {card.channel} to Blast ✓")
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
# Blast tab — queued messages + Nimble-powered people search
# =========================================================================
# =========================================================================
# Search People tab — Nimble-powered audience search + Add to Blast
# =========================================================================
with tab_search:
    st.subheader("Find people to reach out to")
    st.caption(
        "Describe the audience. We search LinkedIn (and the open web for emails) "
        "and return matching profiles. Click **Add to Blast** to queue a target."
    )

    criteria = st.text_input(
        "Audience criteria",
        value=st.session_state.get(
            "blast_criteria",
            "AI research labs in New York, PHD, with research",
        ),
        placeholder="e.g. healthcare AI engineers in San Francisco, hiring",
    )
    col_a, col_b = st.columns([1, 1])
    limit = col_a.slider("How many targets?", min_value=3, max_value=15, value=5)
    include_email = col_b.checkbox("Also search for emails (slower)", value=False)

    if st.button("Find Targets", type="primary", disabled=not _HAS_NIMBLE_KEY):
        st.session_state["blast_criteria"] = criteria
        if not criteria.strip():
            st.warning("Enter a criteria to search.")
        else:
            try:
                nimble = NimbleClient.from_env()
                with st.spinner("Searching via Nimble..."):
                    people = nimble.find_people(criteria, limit=limit)
                    emails: list[dict] = []
                    if include_email and people:
                        for p in people[:3]:
                            name = (p.get("title") or "").split(" - ")[0].strip()
                            if not name:
                                continue
                            try:
                                hits = nimble.search(
                                    f'"{name}" email contact',
                                    focus="general",
                                    max_results=2,
                                )
                                if hits:
                                    emails.append({"name": name, "hits": hits})
                            except NimbleAPIError:
                                pass
                st.session_state["blast_search_results"] = people
                st.session_state["blast_search_emails"] = emails
                st.success(f"Found {len(people)} target(s).")
            except NimbleAPIError as e:
                st.error(f"Nimble error: {e}")
            except KeyError:
                st.error("NIMBLE_API_KEY missing in .env.")

    if not _HAS_NIMBLE_KEY:
        st.caption("`NIMBLE_API_KEY` not set — add it to `.env` to enable target search.")

    results = st.session_state.get("blast_search_results", [])
    if results:
        st.markdown(f"**Results ({len(results)})**")
        targets_added = st.session_state.setdefault("blast_targets_added", [])
        added_urls = {t.get("url") for t in targets_added}
        for j, t in enumerate(results):
            with st.container(border=True):
                title = t.get("title") or "(no title)"
                desc = t.get("description") or ""
                url = t.get("url") or ""
                st.markdown(f"**{title}**")
                if desc:
                    st.caption(desc[:240])
                if url:
                    st.markdown(f"[Open profile →]({url})")
                if url in added_urls:
                    st.success("Added to Blast ✓")
                else:
                    if st.button("Add to Blast", key=f"add_target_{j}"):
                        targets_added.append({
                            "title": title, "description": desc, "url": url,
                        })
                        st.rerun()

    emails = st.session_state.get("blast_search_emails", [])
    if emails:
        st.markdown("**Email leads** (open-web search results)")
        for e in emails:
            with st.expander(e["name"]):
                for h in e.get("hits", []):
                    st.markdown(f"- [{h.get('title','(link)')}]({h.get('url','')}) — {h.get('description','')[:160]}")


# =========================================================================
# Blast tab — Messages + Targets + Personal Resources + Send
# =========================================================================
with tab_blast:
    blast_msgs = st.session_state.get("blast_queue", [])
    blast_targets = st.session_state.get("blast_targets_added", [])

    # ---- Personal Resources picker (papers / GitHub repos / resume) ----
    st.subheader("Attach personal resources")
    st.caption("Pick what to reference in the blast — papers, repos, or your resume.")

    # Papers (from Scholar mock or live fetch)
    scholar_url_for_fetch = st.session_state.get("brand_scholar") or None
    try:
        scholar_data = fetch_scholar(scholar_url_for_fetch)
        all_papers = scholar_data.papers or []
    except Exception:
        all_papers = []

    # GitHub repos (via PyGithub)
    gh_url = st.session_state.get("brand_github", "")
    @st.cache_data(show_spinner=False)
    def _cached_repos(url: str) -> list[dict]:
        return list_user_repos(url) if url else []
    repos = _cached_repos(gh_url) if gh_url else []

    resume_text = st.session_state.get("brand_resume", "")

    res_cols = st.columns([2, 2, 1])
    selected_papers = res_cols[0].multiselect(
        "Papers",
        options=[p["title"] for p in all_papers],
        default=st.session_state.get("blast_res_papers", []),
        placeholder="Search your research papers...",
    )
    st.session_state["blast_res_papers"] = selected_papers

    selected_repos = res_cols[1].multiselect(
        "GitHub repos",
        options=[r["name"] for r in repos],
        default=st.session_state.get("blast_res_repos", []),
        placeholder="Search your GitHub repos...",
    )
    st.session_state["blast_res_repos"] = selected_repos

    attach_resume = res_cols[2].checkbox(
        "Resume",
        value=st.session_state.get("blast_res_resume", False),
        help="Attach your resume text to every send.",
    )
    st.session_state["blast_res_resume"] = attach_resume

    summary_chips: list[str] = []
    if selected_papers:
        summary_chips += [f"📄 {t}" for t in selected_papers]
    if selected_repos:
        summary_chips += [f"🔧 {r}" for r in selected_repos]
    if attach_resume and resume_text:
        summary_chips.append("📋 Resume")
    if summary_chips:
        st.markdown("**Attached:** " + " · ".join(summary_chips))
    if gh_url and not repos:
        st.caption(f"Could not list repos for `{gh_url}` (check GITHUB_TOKEN).")

    st.divider()

    # ---- Messages queue ----
    st.subheader("Messages")
    if not blast_msgs:
        st.info("No messages yet. Generate one on **Generate Content** and click **Add to Blast**.")
    else:
        for i, item in enumerate(blast_msgs):
            with st.expander(f"{i + 1}. {item['channel']}", expanded=(i == 0)):
                st.text_area(
                    "Message",
                    value=item["markdown"],
                    key=f"blast_msg_{i}",
                    height=180,
                )
                if st.button("Remove from queue", key=f"blast_remove_{i}"):
                    blast_msgs.pop(i)
                    st.rerun()
        if st.button("Clear messages"):
            st.session_state["blast_queue"] = []
            st.rerun()

    st.divider()

    # ---- Targets queue ----
    st.subheader("Targets")
    if not blast_targets:
        st.info("No targets yet. Add some on **Search People**.")
    else:
        for k, t in enumerate(blast_targets):
            with st.container(border=True):
                st.markdown(f"**{t.get('title','(no title)')}**")
                if t.get("description"):
                    st.caption(t["description"][:200])
                if t.get("url"):
                    st.markdown(f"[Open profile →]({t['url']})")
                if st.button("Remove", key=f"target_remove_{k}"):
                    blast_targets.pop(k)
                    st.rerun()
        if st.button("Clear targets"):
            st.session_state["blast_targets_added"] = []
            st.rerun()

    st.divider()

    # ---- Send ----
    can_send = bool(blast_msgs) and bool(blast_targets)
    if st.button("🚀 Send Blast", type="primary", disabled=not can_send, use_container_width=True):
        n = len(blast_msgs) * len(blast_targets)
        st.toast(f"Queued {n} sends (demo) ✓")
        st.success(
            f"Blast queued: {len(blast_msgs)} message(s) × {len(blast_targets)} target(s) "
            f"= {n} sends. Resources attached: {len(summary_chips)}."
        )
    if not can_send:
        st.caption("Need at least one message AND one target to send.")
