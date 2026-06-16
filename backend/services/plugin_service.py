"""Plugin extraction service.

Wraps the existing paperpilot plugin pipeline (github_ingest -> skill_extract
-> skill_render) and persists the rendered Claude Code plugin zip to
session_artifacts. No LLM logic lives here; it is delegated to
paperpilot.skill_extract.extract_plugin.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass

from paperpilot import supabase_client
from paperpilot.github_ingest import fetch_repo
from paperpilot.skill_extract import PluginPack, extract_plugin
from paperpilot.skill_render import build_plugin_zip, render_plugin_manifest


@dataclass(frozen=True)
class PluginResult:
    """Outcome of a plugin extraction: name, manifest dict, and zip bytes."""

    plugin_name: str
    manifest: dict
    zip_bytes: bytes


def extract_plugin_from_repo(repo_url: str, user_id: str) -> PluginResult:
    """Fetch a repo, extract a PluginPack, render the plugin zip, and persist it.

    The repo bundle feeds a single Gateway LLM call (in extract_plugin) that
    returns a structured PluginPack, which skill_render turns into an on-disk
    Claude Code plugin layout zipped in memory. The zip is base64-encoded and
    written to session_artifacts as a "plugin" artifact, scoped to the caller.

    Persistence is best-effort: a Supabase write failure must not block the
    user-facing download, matching the convention in insert_artifact.

    Args:
        repo_url: GitHub repository URL to extract the plugin from.
        user_id: Supabase auth UUID of the authenticated caller.

    Returns:
        A PluginResult with the kebab-case plugin name, the parsed manifest,
        and the raw zip bytes for the caller to base64-encode for the response.
    """
    session_id = str(uuid.uuid4())
    source_repo = repo_url.strip()

    bundle = fetch_repo(source_repo)
    pack: PluginPack = extract_plugin(bundle, session_id)
    source_label = f"{bundle.owner}/{bundle.name}"

    zip_bytes = build_plugin_zip(pack, source_label)
    manifest = json.loads(render_plugin_manifest(pack, source_label))
    plugin_name = manifest["name"]

    zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
    content_hash = hashlib.sha256(zip_bytes).hexdigest()

    try:
        supabase_client.insert_artifact(
            session_id,
            user_id,
            "plugin",
            f"{plugin_name}.zip",
            zip_b64,
            repo=source_label,
            metadata={
                "repo_url": source_repo,
                "plugin_name": plugin_name,
                "encoding": "base64",
                "total_artifacts": pack.total_artifacts,
                "counts": {
                    "skills": len(pack.skills),
                    "commands": len(pack.commands),
                    "agents": len(pack.agents),
                    "hooks": len(pack.hooks),
                    "mcps": len(pack.mcps),
                },
            },
            content_hash=content_hash,
        )
    except Exception:  # noqa: BLE001 -- persistence must not block the download
        pass

    return PluginResult(
        plugin_name=plugin_name,
        manifest=manifest,
        zip_bytes=zip_bytes,
    )
