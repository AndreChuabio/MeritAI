"""PaperPilot Streamlit UI.

Two surfaces in one file:
  - Phase 1 hello-world: a "Ping LLM" button to verify Lapdog + Gateway wires
  - Full pipeline: paste GitHub URL -> summary -> ranked CFPs -> paper draft

Launch:
    DD_API_KEY=$DD_API_KEY lapdog streamlit run app.py

Without Lapdog wrap, the app still runs -- it just won't appear in the local
Lapdog dashboard (which is fine for ad-hoc debugging).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from paperpilot import trace
from paperpilot.pipeline import load_demo_cache


load_dotenv()

st.set_page_config(page_title="PaperPilot", page_icon="📄", layout="wide")
st.title("PaperPilot")
st.caption(
    "Drop a GitHub repo. Get a paper drafted for a real venue. "
    "Every LLM call traced in Lapdog."
)

if "session_id" not in st.session_state:
    st.session_state.session_id = trace.new_session()
if "bundle" not in st.session_state:
    st.session_state.bundle = None
if "summary" not in st.session_state:
    st.session_state.summary = None
if "venues" not in st.session_state:
    st.session_state.venues = []
if "chosen_venue" not in st.session_state:
    st.session_state.chosen_venue = None
if "sections" not in st.session_state:
    st.session_state.sections = {}

session_id = st.session_state.session_id


def _env_summary() -> dict[str, str]:
    return {
        "Gateway": "configured" if os.environ.get("AI_GATEWAY_API_KEY") else "missing",
        "ClickHouse": "configured" if os.environ.get("CLICKHOUSE_HOST") else "missing",
        "Datadog forward": "enabled" if os.environ.get("DD_API_KEY") else "off",
        "Demo mode": "on" if os.environ.get("DEMO_MODE", "").lower() == "true" else "off",
    }


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

left, right = st.columns([2, 1])

with right:
    st.subheader("Agent trace")
    st.caption(f"session: `{session_id}`")
    events = trace.buffered_events(session_id)
    if not events:
        st.info("No events yet. Run a stage on the left.")
    else:
        for evt in reversed(events[-30:]):
            with st.container(border=True):
                st.markdown(f"**{evt.kind}**")
                st.caption(f"+{evt.ts:.0f}")
                if evt.payload:
                    st.json(evt.payload, expanded=False)

    st.divider()
    st.markdown("**Sponsor wires**")
    for label, status in _env_summary().items():
        icon = "🟢" if status in {"configured", "enabled", "on"} else "⚪"
        st.write(f"{icon} {label}: `{status}`")
    st.caption("Lapdog dashboard: http://localhost:8126")


with left:
    tab_pipeline, tab_phase1 = st.tabs(["Pipeline", "Phase 1 hello-world"])

    # ------------------------------------------------------------------
    # Phase 1: instrumentation hello-world
    # ------------------------------------------------------------------
    with tab_phase1:
        st.markdown(
            "Smallest unit test of the wires. One AI Gateway call. "
            "Watch the trace panel on the right + the Lapdog dashboard."
        )
        if st.button("Ping LLM", use_container_width=True):
            from paperpilot.llm_ping import ping

            with st.spinner("Calling AI Gateway..."):
                try:
                    text = ping(session_id=session_id)
                    st.success(f"Got {len(text)} chars back.")
                    st.code(text, language="markdown")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Ping failed: {exc}")

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    with tab_pipeline:
        url = st.text_input(
            "GitHub repo URL",
            placeholder="https://github.com/owner/repo",
            help="Public or private repo you have access to via gh CLI.",
        )

        ingest_col, demo_col = st.columns([3, 1])
        with ingest_col:
            ingest_clicked = st.button(
                "Ingest + match venues", type="primary", use_container_width=True
            )
        with demo_col:
            use_demo = st.button("Load demo cache", use_container_width=True)

        if use_demo:
            cache = load_demo_cache()
            if cache is None:
                st.error("No demo cache. Run scripts/demo_precompute.py <url> first.")
            else:
                from paperpilot.llm_ingest import ResearchSummary

                st.session_state.summary = ResearchSummary.model_validate(
                    cache["summary"]
                )
                from datetime import date
                from paperpilot.cfp_match import VenueMatch

                st.session_state.venues = [
                    VenueMatch(
                        id=v["id"],
                        name=v["name"],
                        scope=v["scope"],
                        deadline=date.fromisoformat(v["deadline"]),
                        url=v["url"],
                        fit_score=v["fit_score"],
                        days_until_deadline=v["days_until_deadline"],
                    )
                    for v in cache["venues"]
                ]
                st.session_state.chosen_venue = st.session_state.venues[0]
                trace.log_event(
                    session_id,
                    "demo.cache_loaded",
                    {"url": cache["url"], "venues": len(cache["venues"])},
                )

        if ingest_clicked and url:
            from paperpilot.pipeline import ingest_and_match

            with st.status("Stage 1 + 2: ingest -> match", expanded=True) as status:
                try:
                    bundle, summary, venues = ingest_and_match(url, session_id)
                    st.session_state.bundle = bundle
                    st.session_state.summary = summary
                    st.session_state.venues = venues
                    st.session_state.chosen_venue = venues[0] if venues else None
                    st.session_state.sections = {}
                    status.update(label="Ingest + match done", state="complete")
                except Exception as exc:  # noqa: BLE001
                    status.update(label=f"Failed: {exc}", state="error")
                    st.exception(exc)

        # Render the structured summary
        if st.session_state.summary is not None:
            s = st.session_state.summary
            with st.expander("Research summary (Gemini 1M-ctx)", expanded=True):
                st.markdown(f"**Problem.** {s.problem}")
                st.markdown(f"**Contribution.** {s.contribution}")
                st.markdown(f"**Method.** {s.method}")
                st.markdown(f"**Results.** {s.results}")
                st.markdown(f"**Limitations.** {s.limitations}")
                if s.keywords:
                    st.write("**Keywords:**", " · ".join(s.keywords))
                if s.venue_hints:
                    st.write("**Venue hints:**", " · ".join(s.venue_hints))

        # Render the venue cards
        if st.session_state.venues:
            st.subheader("Top matched venues")
            cols = st.columns(min(len(st.session_state.venues), 3))
            for i, venue in enumerate(st.session_state.venues):
                col = cols[i % len(cols)]
                with col:
                    with st.container(border=True):
                        st.markdown(f"**{venue.name}**")
                        st.caption(f"fit `{venue.fit_score:.3f}` · {venue.days_until_deadline} days")
                        st.write(venue.scope[:160] + ("..." if len(venue.scope) > 160 else ""))
                        if st.button(f"Draft for {venue.name}", key=f"draft_{venue.id}"):
                            st.session_state.chosen_venue = venue
                            st.session_state.sections = {}

        # Draft the paper
        if (
            st.session_state.summary is not None
            and st.session_state.chosen_venue is not None
        ):
            st.subheader(f"Drafting for {st.session_state.chosen_venue.name}")
            if not st.session_state.sections:
                from paperpilot.draft import draft_paper, SECTIONS

                section_placeholders = {s: st.empty() for s in SECTIONS}
                buffers = {s: "" for s in SECTIONS}
                gen = draft_paper(
                    st.session_state.summary,
                    st.session_state.chosen_venue,
                    session_id,
                )
                try:
                    while True:
                        sec, delta = next(gen)
                        buffers[sec] += delta
                        section_placeholders[sec].markdown(
                            f"**{sec.title()}**\n\n{buffers[sec]}"
                        )
                except StopIteration as stop:
                    st.session_state.sections = stop.value

            if st.session_state.sections:
                # LaTeX export
                from paperpilot.latex_export import export_paper

                tex, bib = export_paper(
                    st.session_state.summary,
                    st.session_state.chosen_venue,
                    st.session_state.sections,
                )
                ex_col1, ex_col2 = st.columns(2)
                with ex_col1:
                    st.download_button(
                        "Download paperpilot.tex",
                        tex,
                        file_name="paperpilot.tex",
                        mime="application/x-tex",
                        use_container_width=True,
                    )
                with ex_col2:
                    st.download_button(
                        "Download references.bib",
                        bib,
                        file_name="references.bib",
                        mime="application/x-bibtex",
                        use_container_width=True,
                    )
                related = st.session_state.sections.get("related")
                if related and related.stripped_ids:
                    st.warning(
                        f"Stripped {len(related.stripped_ids)} unapproved citations: "
                        + ", ".join(related.stripped_ids[:5])
                    )
