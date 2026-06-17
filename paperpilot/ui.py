"""Merit UI helpers.

Presentation-only module. Holds the global CSS blob and a small set of
render helpers used across Productize, Market, and Track. Keep this tight:
no class hierarchies, just functions that return strings or call
``st.markdown(...)``.

Design tokens (mirror what is in CSS):
    --bg-base:      #0A0A0A
    --bg-raise:     #111111
    --surface:      #161616
    --surface-2:    #1F1F1F
    --border:       #262626
    --border-hover: #3F3F46
    --fg:           #F5F5F5
    --fg-muted:     #A1A1AA
    --fg-dim:       #71717A
    --accent-from:  #6366F1
    --accent-to:    #8B5CF6
    --success:      #22C55E
    --warning:      #F59E0B
    --error:        #EF4444
    --font-ui:      Inter
    --font-mono:    JetBrains Mono

The single mutable contract is :func:`inject_global_css` which must be
called once at the top of every page. The rest of the helpers can be
called multiple times.
"""

from __future__ import annotations

import html
import json
from typing import Any, Mapping, Optional

import streamlit as st


# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------

_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg-base: #0A0A0A;
    --bg-raise: #111111;
    --surface: #161616;
    --surface-2: #1F1F1F;
    --border: #262626;
    --border-hover: #3F3F46;
    --fg: #F5F5F5;
    --fg-muted: #A1A1AA;
    --fg-dim: #71717A;
    --accent-from: #6366F1;
    --accent-to: #8B5CF6;
    --success: #22C55E;
    --warning: #F59E0B;
    --error: #EF4444;
    --font-ui: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}

html, body, [class*="css"], .stApp, .stMarkdown, .stText {
    font-family: var(--font-ui) !important;
    background-color: var(--bg-base);
    color: var(--fg);
}

.stApp {
    background:
        radial-gradient(1200px 600px at 80% -10%, rgba(139, 92, 246, 0.08), transparent 60%),
        radial-gradient(900px 500px at -10% 0%, rgba(99, 102, 241, 0.06), transparent 60%),
        var(--bg-base);
}

/* Headings: sharp, tight tracking */
h1, h2, h3, h4 {
    font-family: var(--font-ui) !important;
    color: var(--fg);
    letter-spacing: -0.02em;
    font-weight: 700;
}
h1 { font-size: 2.0rem; line-height: 1.15; }
h2 { font-size: 1.4rem; line-height: 1.2; }
h3 { font-size: 1.1rem; line-height: 1.25; }

/* Caption + secondary text */
.stCaption, .stMarkdown small, [data-testid="stCaptionContainer"] {
    color: var(--fg-muted) !important;
    font-size: 0.82rem !important;
}

/* ------------------------------------------------------------------
   Sidebar — real nav: title at top, items with hover + active state
   ------------------------------------------------------------------ */
[data-testid="stSidebar"] {
    background-color: #0C0C0C !important;
    border-right: 1px solid var(--border);
    width: 220px !important;
    min-width: 220px !important;
    max-width: 220px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0.6rem;
}
[data-testid="stSidebarNav"] {
    padding-top: 0.4rem;
}
[data-testid="stSidebarNav"] a {
    color: var(--fg-muted) !important;
    border-radius: 6px;
    padding: 8px 12px !important;
    margin: 2px 8px !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    border-left: 2px solid transparent;
    transition: all 120ms ease;
}
[data-testid="stSidebarNav"] a:hover {
    background-color: var(--surface);
    color: var(--fg) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background-color: var(--surface);
    color: var(--fg) !important;
    border-left: 2px solid var(--accent-to);
}
[data-testid="stSidebarNav"] span {
    font-family: var(--font-ui) !important;
}

/* ------------------------------------------------------------------
   Inputs — text, textarea, select
   ------------------------------------------------------------------ */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
.stDateInput input,
[data-baseweb="select"] > div {
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--fg) !important;
    font-family: var(--font-ui) !important;
    transition: border-color 120ms ease, box-shadow 120ms ease;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: var(--accent-to) !important;
    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15) !important;
    outline: none !important;
}
.stTextInput label,
.stTextArea label,
.stSelectbox label,
.stMultiSelect label,
.stRadio label,
.stCheckbox label,
.stSlider label {
    color: var(--fg-muted) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

/* ------------------------------------------------------------------
   Buttons — default + primary (gradient)
   ------------------------------------------------------------------ */
.stButton > button,
.stDownloadButton > button {
    background-color: var(--surface) !important;
    color: var(--fg) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    padding: 0.45rem 0.9rem !important;
    font-family: var(--font-ui) !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    transition: all 120ms ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
    background-color: var(--surface-2) !important;
    border-color: var(--border-hover) !important;
    color: var(--fg) !important;
}
.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
    border: 1px solid rgba(139, 92, 246, 0.5) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.04) inset;
}
.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover {
    filter: brightness(1.08);
    box-shadow: 0 4px 16px rgba(139, 92, 246, 0.25), 0 0 0 1px rgba(255, 255, 255, 0.06) inset;
}

/* ------------------------------------------------------------------
   Tabs — accent-underlined active tab
   ------------------------------------------------------------------ */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid var(--border);
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--fg-muted) !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 18px !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    transition: color 120ms ease, border-color 120ms ease;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--fg) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--fg) !important;
    border-bottom: 2px solid var(--accent-to) !important;
}

/* ------------------------------------------------------------------
   Metric — KPI tile
   ------------------------------------------------------------------ */
[data-testid="stMetric"] {
    background-color: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
}
[data-testid="stMetricLabel"] {
    color: var(--fg-muted) !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stMetricValue"] {
    color: var(--fg) !important;
    font-weight: 700 !important;
    font-size: 1.6rem !important;
}
[data-testid="stMetricDelta"] {
    color: var(--fg-dim) !important;
}

/* ------------------------------------------------------------------
   Containers + expanders + status — dark card surface
   ------------------------------------------------------------------ */
[data-testid="stExpander"],
[data-testid="stExpander"] details {
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    color: var(--fg) !important;
    font-weight: 500 !important;
}
[data-testid="stExpander"] summary:hover {
    color: var(--fg) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: var(--surface);
    border: 1px solid var(--border) !important;
    border-radius: 8px;
    transition: border-color 160ms ease, box-shadow 160ms ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: var(--border-hover) !important;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
}

[data-testid="stStatusWidget"], .stAlert {
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--fg) !important;
}

/* ------------------------------------------------------------------
   Progress bar — gradient fill
   ------------------------------------------------------------------ */
.stProgress > div > div > div > div {
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
    border-radius: 999px;
}
.stProgress > div > div > div {
    background-color: var(--surface-2) !important;
    border-radius: 999px;
    height: 10px !important;
}

/* ------------------------------------------------------------------
   Code blocks + monospace surfaces
   ------------------------------------------------------------------ */
code, pre, .stCode, .stJson {
    font-family: var(--font-mono) !important;
}
.stCode, [data-testid="stCode"] {
    background-color: #0F0F0F !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}

/* ------------------------------------------------------------------
   Merit custom components
   ------------------------------------------------------------------ */
.pp-hero {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 18px 0 4px 0;
}
.pp-hero-glyph {
    width: 44px;
    height: 44px;
    border-radius: 10px;
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 24px rgba(139, 92, 246, 0.35);
}
.pp-hero-glyph svg { width: 22px; height: 22px; }
.pp-hero h1 { margin: 0; }
.pp-hero p { margin: 4px 0 0; color: var(--fg-muted); font-size: 0.95rem; }

.pp-sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 12px 14px 12px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 6px;
}
.pp-sidebar-brand .pp-glyph-sm {
    width: 26px; height: 26px; border-radius: 7px;
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%);
    display: inline-flex; align-items: center; justify-content: center;
    box-shadow: 0 2px 10px rgba(139, 92, 246, 0.35);
}
.pp-sidebar-brand .pp-brand-text {
    font-weight: 700;
    color: var(--fg);
    letter-spacing: -0.01em;
    font-size: 0.98rem;
}

.pp-chip {
    display: inline-flex;
    align-items: center;
    background-color: var(--surface);
    border: 1px solid var(--border);
    color: var(--fg-muted);
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-family: var(--font-mono);
    margin-right: 6px;
}

.pp-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-family: var(--font-ui);
}
.pp-badge-curated { background: rgba(99, 102, 241, 0.15); color: #A5B4FC; border: 1px solid rgba(99, 102, 241, 0.3); }
.pp-badge-live    { background: rgba(251, 146, 60, 0.15); color: #FDBA74; border: 1px solid rgba(251, 146, 60, 0.3); }
.pp-badge-success { background: rgba(34, 197, 94, 0.15); color: #86EFAC; border: 1px solid rgba(34, 197, 94, 0.3); }
.pp-badge-warn    { background: rgba(245, 158, 11, 0.15); color: #FCD34D; border: 1px solid rgba(245, 158, 11, 0.3); }
.pp-badge-error   { background: rgba(239, 68, 68, 0.15);  color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.3); }
.pp-badge-muted   { background: var(--surface-2); color: var(--fg-muted); border: 1px solid var(--border); }

.pp-card {
    background-color: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
    transition: border-color 160ms ease, box-shadow 160ms ease;
}
.pp-card:hover {
    border-color: var(--border-hover);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
}
.pp-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
}
.pp-card-title {
    font-weight: 600;
    color: var(--fg);
    font-size: 0.98rem;
}
.pp-card-meta {
    color: var(--fg-dim);
    font-size: 0.78rem;
    font-family: var(--font-mono);
    margin-bottom: 8px;
}
.pp-card-body {
    color: var(--fg-muted);
    font-size: 0.88rem;
    line-height: 1.5;
}

/* Trace event row — monospace, status dot, timestamp */
.pp-trace-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    background-color: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    margin-bottom: 6px;
    font-family: var(--font-mono);
    font-size: 0.78rem;
}
.pp-trace-row:hover { border-color: var(--border-hover); }
.pp-trace-dot {
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0;
    box-shadow: 0 0 8px currentColor;
}
.pp-trace-dot.start { background: var(--warning); color: var(--warning); }
.pp-trace-dot.end   { background: var(--success); color: var(--success); }
.pp-trace-dot.error { background: var(--error);   color: var(--error); }
.pp-trace-dot.info  { background: var(--fg-dim);  color: var(--fg-dim); }
.pp-trace-name {
    color: var(--fg);
    font-weight: 500;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.pp-trace-ts {
    color: var(--fg-dim);
    font-size: 0.72rem;
}

/* Evidence icon square (Track) */
.pp-evidence-icon {
    width: 28px; height: 28px;
    background-color: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.95rem;
    margin-right: 8px;
}

/* Section divider tightening */
hr { border-color: var(--border) !important; opacity: 0.6; margin: 1.2rem 0 !important; }

/* Reduce default top padding so the hero sits close to the top */
.block-container { padding-top: 2.2rem !important; }
</style>
"""


def inject_global_css() -> None:
    """Inject the global stylesheet. Call once at the top of every page."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

_DIAMOND_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M12 2L22 12L12 22L2 12L12 2Z" fill="white" fill-opacity="0.95"/>'
    '<path d="M12 7L17 12L12 17L7 12L12 7Z" fill="url(#g)" fill-opacity="0.35"/>'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24" '
    'gradientUnits="userSpaceOnUse">'
    '<stop stop-color="#6366F1"/><stop offset="1" stop-color="#8B5CF6"/>'
    '</linearGradient></defs></svg>'
)


def hero(title: str, subtitle: Optional[str] = None) -> None:
    """Render the hero header with the diamond glyph + title + subtitle."""
    sub = (
        f'<p>{html.escape(subtitle)}</p>' if subtitle else ""
    )
    st.markdown(
        f'<div class="pp-hero">'
        f'<div class="pp-hero-glyph">{_DIAMOND_SVG}</div>'
        f'<div><h1>{html.escape(title)}</h1>{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def sidebar_brand(label: str = "Merit") -> None:
    """Render the sidebar brand block (diamond + name) above the nav."""
    st.markdown(
        f'<div class="pp-sidebar-brand">'
        f'<span class="pp-glyph-sm">{_DIAMOND_SVG}</span>'
        f'<span class="pp-brand-text">{html.escape(label)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def chip(label: str) -> str:
    """Return a chip HTML span (callers wrap in markdown)."""
    return f'<span class="pp-chip">{html.escape(label)}</span>'


def badge(label: str, variant: str = "muted") -> str:
    """Return a badge HTML span.

    ``variant`` is one of: ``curated``, ``live``, ``success``, ``warn``,
    ``error``, ``muted``.
    """
    cls = {
        "curated": "pp-badge-curated",
        "live": "pp-badge-live",
        "success": "pp-badge-success",
        "warn": "pp-badge-warn",
        "error": "pp-badge-error",
        "muted": "pp-badge-muted",
    }.get(variant, "pp-badge-muted")
    return f'<span class="pp-badge {cls}">{html.escape(label)}</span>'


def card(title: str, body: str, badge_html: Optional[str] = None,
         meta: Optional[str] = None) -> None:
    """Render a dark-themed card block.

    ``title``: card heading (required).
    ``body``: HTML or text body (already escaped by caller if needed).
    ``badge_html``: optional pre-rendered badge HTML (from :func:`badge`).
    ``meta``: optional muted monospace line under the title.
    """
    head_right = badge_html or ""
    meta_html = f'<div class="pp-card-meta">{meta}</div>' if meta else ""
    st.markdown(
        f'<div class="pp-card">'
        f'<div class="pp-card-head">'
        f'<div class="pp-card-title">{html.escape(title)}</div>'
        f'{head_right}'
        f'</div>'
        f'{meta_html}'
        f'<div class="pp-card-body">{body}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def metric_tile(label: str, value: str, hint: Optional[str] = None) -> None:
    """Render a metric tile. Wraps ``st.metric`` for consistency with the theme."""
    st.metric(label=label, value=value, help=hint)


def gradient_button(label: str, key: str, disabled: bool = False,
                    use_container_width: bool = True) -> bool:
    """Render the primary gradient CTA. Returns the same bool as ``st.button``.

    Backed by ``st.button(type="primary")`` so the gradient comes from
    the global stylesheet rather than per-call styling.
    """
    return st.button(
        label,
        key=key,
        type="primary",
        disabled=disabled,
        use_container_width=use_container_width,
    )


_TRACE_STATUS_CLASS = {
    "start": "start",
    "end": "end",
    "error": "error",
    "info": "info",
}


def _format_payload(payload: Mapping[str, Any]) -> str:
    """Pretty-print a payload, stable key order, two spaces of indent."""
    try:
        return json.dumps(dict(payload), indent=2, default=str, sort_keys=False)
    except (TypeError, ValueError):
        return str(payload)


def trace_event(name: str, payload: Mapping[str, Any], status: str = "end",
                ts: Optional[float] = None) -> None:
    """Render one trace event row + expandable payload.

    ``name``: event kind, e.g. ``"draft.abstract.end"``.
    ``payload``: dict serialised under the expander.
    ``status``: one of ``start``, ``end``, ``error``, ``info``.
    ``ts``: seconds-since-session-start, optional.
    """
    dot_cls = _TRACE_STATUS_CLASS.get(status, "info")
    ts_html = f'<span class="pp-trace-ts">+{ts:.1f}s</span>' if ts is not None else ""
    st.markdown(
        f'<div class="pp-trace-row">'
        f'<span class="pp-trace-dot {dot_cls}"></span>'
        f'<span class="pp-trace-name">{html.escape(name)}</span>'
        f'{ts_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if payload:
        with st.expander("payload", expanded=False):
            st.code(_format_payload(payload), language="json")


def venue_card(name: str, scope: str, fit_score: float, days_until: int,
               is_live: bool, source_url: Optional[str] = None) -> None:
    """Render one venue card (Productize page).

    Mirrors the inline card-rendering in ``Productize.py`` but as a single
    helper. The ``Draft for X`` button is NOT rendered here so callers can
    keep ownership of the ``st.button`` key + state mutation.
    """
    badge_html = (
        badge("LIVE - Nimble", "live") if is_live else badge("Curated", "curated")
    )
    body_text = scope[:160] + ("..." if len(scope) > 160 else "")
    source_line = (
        f'<div style="margin-top:8px;"><a href="{html.escape(source_url)}" '
        f'style="color: var(--fg-dim); font-size: 0.78rem; '
        f'font-family: var(--font-mono);">live source</a></div>'
        if (is_live and source_url) else ""
    )
    meta = f"fit {fit_score:.3f}  -  {days_until} days to deadline"
    st.markdown(
        f'<div class="pp-card">'
        f'<div class="pp-card-head">'
        f'<div class="pp-card-title">{html.escape(name)}</div>'
        f'{badge_html}'
        f'</div>'
        f'<div class="pp-card-meta">{html.escape(meta)}</div>'
        f'<div class="pp-card-body">{html.escape(body_text)}</div>'
        f'{source_line}'
        f'</div>',
        unsafe_allow_html=True,
    )


def evidence_tile(icon: str, label: str, value: str,
                  hint: Optional[str] = None) -> None:
    """Render an evidence-by-category tile (Track page).

    The emoji ``icon`` sits in a small rounded square at the top-left of the
    tile. Value is the headline number, label is small + muted underneath.
    """
    hint_html = (
        f'<div style="margin-top:8px; color: var(--fg-dim); '
        f'font-size: 0.75rem; line-height: 1.4;">{html.escape(hint)}</div>'
        if hint else ""
    )
    st.markdown(
        f'<div class="pp-card" style="margin-bottom: 0;">'
        f'<div style="display:flex; align-items:center; gap:10px;">'
        f'<span class="pp-evidence-icon">{html.escape(icon)}</span>'
        f'<span style="color: var(--fg-muted); font-size: 0.78rem; '
        f'font-weight: 500; text-transform: uppercase; '
        f'letter-spacing: 0.04em;">{html.escape(label)}</span>'
        f'</div>'
        f'<div style="font-size: 1.75rem; font-weight: 700; color: var(--fg); '
        f'margin-top: 8px;">{html.escape(value)}</div>'
        f'{hint_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def section_heading(label: str, hint: Optional[str] = None) -> None:
    """Render a subsection heading with optional muted hint underneath."""
    st.markdown(
        f'<div style="margin: 18px 0 8px 0;">'
        f'<div style="font-weight: 600; font-size: 1.05rem; '
        f'color: var(--fg); letter-spacing: -0.01em;">{html.escape(label)}</div>'
        + (
            f'<div style="color: var(--fg-muted); font-size: 0.82rem; '
            f'margin-top: 2px;">{html.escape(hint)}</div>' if hint else ""
        )
        + '</div>',
        unsafe_allow_html=True,
    )
