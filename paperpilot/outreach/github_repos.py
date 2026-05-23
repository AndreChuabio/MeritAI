"""List a user's public GitHub repos for the Blast resource picker.

Uses PyGithub (already a project dep). Token comes from GITHUB_TOKEN.
Best-effort: on any failure returns an empty list so the UI does not crash.
"""

from __future__ import annotations

import os
from typing import Optional

from github import Github


def extract_username(github_url: str) -> Optional[str]:
    """Pull the username segment out of a GitHub profile URL."""
    if not github_url:
        return None
    stripped = github_url.strip().rstrip("/")
    if not stripped:
        return None
    return stripped.rsplit("/", 1)[-1] or None


def list_user_repos(
    github_url: str,
    token: str | None = None,
    limit: int = 30,
) -> list[dict]:
    """Return the user's top public repos as [{name, url, description, stars, language}]."""
    username = extract_username(github_url)
    if not username:
        return []
    token = token or os.environ.get("GITHUB_TOKEN")
    try:
        g = Github(token) if token else Github()
        user = g.get_user(username)
        repos = list(user.get_repos()[:limit])
    except Exception:
        return []
    out: list[dict] = []
    for r in repos:
        try:
            out.append({
                "name": r.name,
                "url": r.html_url,
                "description": r.description or "",
                "stars": int(getattr(r, "stargazers_count", 0) or 0),
                "language": r.language or "",
            })
        except Exception:
            continue
    return out
