"""Plugin extraction router.

Exposes POST /extract-plugin: given a GitHub repo URL, extract a publishable
Claude Code plugin and return its name, manifest, and the rendered plugin
directory as a base64-encoded zip. Auth required.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.auth import AuthUser, CurrentUser
from backend.byok import RequireLLMKey
from backend.services.plugin_service import extract_plugin_from_repo

router = APIRouter(tags=["plugin"])


class ExtractPluginRequest(BaseModel):
    """Request body for plugin extraction."""

    repo_url: str


class ExtractPluginResponse(BaseModel):
    """Rendered Claude Code plugin: name, manifest, and base64 zip."""

    plugin_name: str
    manifest: dict
    zip_base64: str


@router.post("/extract-plugin", response_model=ExtractPluginResponse)
def extract_plugin_endpoint(
    req: ExtractPluginRequest,
    user: AuthUser = CurrentUser,
    _: None = RequireLLMKey,
) -> ExtractPluginResponse:
    """Extract a Claude Code plugin from a GitHub repo and return it zipped.

    Fetches the repo bundle, runs the LLM plugin extraction, renders the
    plugin directory to a zip, persists it to session_artifacts under the
    caller, and returns the zip base64-encoded for download.
    """
    repo_url = req.repo_url.strip()
    if not repo_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repo_url is required",
        )

    try:
        result = extract_plugin_from_repo(repo_url, user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001 -- surface pipeline errors as 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plugin extraction failed: {exc}",
        ) from exc

    return ExtractPluginResponse(
        plugin_name=result.plugin_name,
        manifest=result.manifest,
        zip_base64=base64.b64encode(result.zip_bytes).decode("ascii"),
    )
