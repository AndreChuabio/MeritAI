"""Supabase Auth integration for the FastAPI backend.

A request authenticates with a Supabase access token (JWT) in the
Authorization header. We validate it by calling the Supabase Auth server's
/auth/v1/user endpoint, which verifies the signature and expiry and returns
the user record. This works regardless of the project's JWT signing algorithm
(legacy HS256 secret or asymmetric keys) and needs no signing secret in the
backend. Validated users are cached briefly to avoid a round-trip per request.

The returned user's id (a Supabase auth UUID) is the user_id threaded through
every data-layer call, matching the auth.users(id) foreign keys in the schema.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, Header, HTTPException, status

# Short-lived validation cache: token -> (user, expires_at_monotonic).
_CACHE: dict[str, tuple["AuthUser", float]] = {}
_CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class AuthUser:
    """The authenticated caller. id is the Supabase auth UUID = user_id."""

    id: str
    email: str | None


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUPABASE_URL is not configured",
        )
    return url.rstrip("/")


def _anon_key() -> str:
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUPABASE_ANON_KEY is not configured",
        )
    return key


async def _validate_token(token: str) -> AuthUser:
    """Validate a Supabase access token, returning the authenticated user."""
    now = time.monotonic()
    cached = _CACHE.get(token)
    if cached and cached[1] > now:
        return cached[0]

    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            f"{_supabase_url()}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": _anon_key()},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    data = resp.json()
    user = AuthUser(id=data["id"], email=data.get("email"))
    _CACHE[token] = (user, now + _CACHE_TTL_SECONDS)
    return user


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> AuthUser:
    """FastAPI dependency: extract and validate the bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    return await _validate_token(token)


# Convenience annotation for route signatures.
CurrentUser = Depends(get_current_user)
