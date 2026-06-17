"""Passcode-style auth shim for Merit.

Two real users (Andre and Nikki) plus a dev fallback. Designed as a temporary
shim that can be swapped for a real provider (Clerk on Vercel Marketplace was
the leading candidate at audit time) without changing call sites.

Contract used by every Streamlit page:

    from paperpilot.auth import require_auth
    user_id = require_auth()
    # st.session_state["user_id"] and st.session_state["user_name"] now set.

Configuration:
    PAPERPILOT_USERS_JSON -- JSON list of users. Schema:
        [{"user_id": "andre", "name": "Andre", "passcode": "..."},
         {"user_id": "nikki", "name": "Nikki", "passcode": "..."}]

If the env var is unset, empty, or invalid JSON, the module falls back to a
single dev user (user_id="dev", passcode="dev") and surfaces a Streamlit
warning so the degradation is visible in production.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from typing import List, Optional, TypedDict

import streamlit as st

logger = logging.getLogger(__name__)


class _UserRecord(TypedDict):
    """Internal shape of a configured user record."""

    user_id: str
    name: str
    passcode: str


_DEV_USER: _UserRecord = {"user_id": "dev", "name": "Dev", "passcode": "dev"}
_USERS_ENV_VAR = "PAPERPILOT_USERS_JSON"


def _load_users() -> tuple[List[_UserRecord], bool]:
    """Load user records from the environment.

    Returns a tuple of (users, is_dev_fallback). ``is_dev_fallback`` is True
    when the env var is unset, empty, malformed, or contains no valid records.
    A dev fallback always yields exactly one user (the built-in dev account).
    """
    raw = os.environ.get(_USERS_ENV_VAR, "").strip()
    if not raw:
        return [dict(_DEV_USER)], True  # type: ignore[list-item]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("PAPERPILOT_USERS_JSON is not valid JSON: %s", exc)
        return [dict(_DEV_USER)], True  # type: ignore[list-item]

    if not isinstance(parsed, list) or not parsed:
        logger.warning(
            "PAPERPILOT_USERS_JSON must be a non-empty JSON list; got %s",
            type(parsed).__name__,
        )
        return [dict(_DEV_USER)], True  # type: ignore[list-item]

    users: List[_UserRecord] = []
    for idx, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            logger.warning("Skipping user at index %d: not an object", idx)
            continue
        user_id = entry.get("user_id")
        name = entry.get("name")
        passcode = entry.get("passcode")
        if not (
            isinstance(user_id, str)
            and isinstance(name, str)
            and isinstance(passcode, str)
            and user_id
            and name
            and passcode
        ):
            logger.warning(
                "Skipping user at index %d: missing user_id/name/passcode", idx
            )
            continue
        users.append({"user_id": user_id, "name": name, "passcode": passcode})

    if not users:
        logger.warning("PAPERPILOT_USERS_JSON contained no valid user records")
        return [dict(_DEV_USER)], True  # type: ignore[list-item]

    return users, False


def _find_user_by_name(users: List[_UserRecord], name: str) -> Optional[_UserRecord]:
    """Locate a user record by display name. Returns None if not found."""
    for user in users:
        if user["name"] == name:
            return user
    return None


def _render_login_form(users: List[_UserRecord], is_dev_fallback: bool) -> None:
    """Render the passcode entry form and handle a single submit cycle.

    On a successful submit, this function mutates ``st.session_state`` and
    calls ``st.rerun()``. On failure it calls ``st.error`` and returns so
    the caller can ``st.stop()`` the page render.
    """
    if is_dev_fallback:
        st.warning(
            "Running in dev auth mode -- no PAPERPILOT_USERS_JSON configured"
        )

    # Centered container so it reads as an intentional sign-in screen.
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        st.markdown("## Merit")
        st.caption("Sign in to continue.")

        names = [user["name"] for user in users]
        with st.form("paperpilot_auth_form", clear_on_submit=False):
            selected_name = st.selectbox("Name", names, index=0)
            passcode_input = st.text_input("Passcode", type="password")
            submitted = st.form_submit_button("Sign in")

        if submitted:
            candidate = _find_user_by_name(users, selected_name)
            supplied = (passcode_input or "").strip()
            if candidate is not None and hmac.compare_digest(
                candidate["passcode"], supplied
            ):
                st.session_state["user_id"] = candidate["user_id"]
                st.session_state["user_name"] = candidate["name"]
                st.rerun()
            else:
                st.error("Invalid passcode")


def require_auth() -> str:
    """Gate a Streamlit page on authentication.

    Returns the authenticated ``user_id``. If no user is in session state,
    renders the passcode form and calls ``st.stop()`` so the rest of the
    page does not execute. After a successful submit the page is re-run
    and this function returns the new ``user_id``.
    """
    user_id = st.session_state.get("user_id")
    if isinstance(user_id, str) and user_id:
        return user_id

    users, is_dev_fallback = _load_users()
    _render_login_form(users, is_dev_fallback)
    st.stop()
    # st.stop() raises; this return is unreachable but keeps type checkers happy.
    return ""  # pragma: no cover


def sign_out() -> None:
    """Clear the authenticated session and re-run the app.

    Intended to be wired to a sidebar button. Safe to call when no user is
    signed in -- the keys are popped defensively.
    """
    st.session_state.pop("user_id", None)
    st.session_state.pop("user_name", None)
    st.rerun()


def current_user() -> Optional[str]:
    """Return the current ``user_id`` without forcing authentication.

    Use this in code paths that want to read the user when present but
    must not block rendering (e.g., trace event tagging in shared
    utilities). Returns ``None`` if no user is in session state.
    """
    value = st.session_state.get("user_id")
    if isinstance(value, str) and value:
        return value
    return None
