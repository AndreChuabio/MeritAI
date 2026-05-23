"""PaperPilot Streamlit entry point.

Phase 1 surface: a "Ping LLM" button that proves the wires.
  - Calls AI Gateway (Lapdog catches it; DD_API_KEY forwards to Datadog cloud)
  - Logs the prompt/response to ClickHouse trace_log
  - Renders the in-process trace buffer live

Launch:
  DD_API_KEY=$DD_API_KEY lapdog streamlit run app.py
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from paperpilot import trace

load_dotenv()

st.set_page_config(page_title="PaperPilot", page_icon="📄", layout="wide")
st.title("PaperPilot")
st.caption("Drop a GitHub repo. Get a paper. Every LLM call traced in Lapdog.")

# Persist a session id across reruns so the trace panel accumulates events
# for the entire user session, not just the latest button click.
if "session_id" not in st.session_state:
    st.session_state.session_id = trace.new_session()

session_id = st.session_state.session_id
left, right = st.columns([2, 1])

with left:
    st.subheader("Phase 1 — instrumentation hello-world")
    st.caption("This panel will become the repo-input + paper-draft view in Phase 2-4.")

    if st.button("Ping LLM (hello-world)"):
        # Lazy import so the module loads even before AI Gateway is configured.
        from paperpilot.llm_ping import ping

        with st.spinner("Calling AI Gateway..."):
            result = ping(session_id=session_id)
        st.success(f"Got {len(result)} chars back from the model.")
        st.code(result[:400] + ("…" if len(result) > 400 else ""), language="markdown")

with right:
    st.subheader("Agent trace")
    st.caption(f"session: `{session_id}`")
    events = trace.buffered_events(session_id)
    if not events:
        st.info("No events yet. Click 'Ping LLM' to generate one.")
    else:
        for evt in reversed(events):
            with st.container(border=True):
                st.markdown(f"**{evt.kind}**")
                st.caption(f"{evt.ts:.3f}")
                st.json(evt.payload, expanded=False)

    st.divider()
    st.caption("Lapdog dashboard: http://localhost:8126")
    st.caption(
        f"DD cloud forward: {'enabled' if os.environ.get('DD_API_KEY') else 'disabled'}"
    )
