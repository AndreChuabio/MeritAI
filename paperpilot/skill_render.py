"""Pure-function rendering of ExtractableSkill -> publishable artifacts.

Two artifacts per skill:
  1. SKILL.md -- frontmatter + body, ready to drop into ~/.claude/skills/<name>/
     and be discovered by Claude Code / claude.ai.
  2. mcp_build_prompt.md -- a prompt the user hands to Claude Code in a new
     session that says "build me an MCP server exposing this skill as tools."
     Includes source file references, suggested tool signatures, and enough
     context for the agent to do the build autonomously.

No LLM calls. Pure templating.
"""

from __future__ import annotations

import io
import re
import zipfile

from paperpilot.skill_extract import ExtractableSkill, SkillPack


_SAFE_NAME_RE = re.compile(r"[^a-z0-9_]+")


def _safe_name(name: str) -> str:
    """Coerce arbitrary text into a directory-safe snake_case identifier."""
    s = name.strip().lower().replace("-", "_").replace(" ", "_")
    s = _SAFE_NAME_RE.sub("", s)
    return s or "unnamed_skill"


def render_skill_md(skill: ExtractableSkill, source_repo: str) -> str:
    """Render a Claude SKILL.md with frontmatter and body."""
    desc = skill.description.replace("\n", " ").strip()
    body_lines = [
        "---",
        f"name: {_safe_name(skill.name)}",
        f"description: {desc}",
        "metadata:",
        f"  kind: {skill.kind}",
        f"  effort: {skill.effort}",
        f"  source_repo: {source_repo}",
        "---",
        "",
        f"# {skill.name}",
        "",
        f"**Source:** {source_repo}",
        "",
        "## What this skill does",
        "",
        skill.description.strip(),
        "",
        "## Why extract it",
        "",
        skill.rationale.strip(),
        "",
    ]

    if skill.source_files:
        body_lines += [
            "## Source files in the original repo",
            "",
            *(f"- `{p}`" for p in skill.source_files),
            "",
        ]

    if skill.key_functions:
        body_lines += [
            "## Key functions / classes",
            "",
            *(f"- `{fn}`" for fn in skill.key_functions),
            "",
        ]

    if skill.suggested_tool_signatures:
        body_lines += ["## Suggested tool signatures", ""]
        for sig in skill.suggested_tool_signatures:
            body_lines.append(f"- `{sig.name}{sig.args}` -- {sig.summary}")
        body_lines.append("")

    if skill.dependencies:
        body_lines += [
            "## Dependencies",
            "",
            *(f"- `{d}`" for d in skill.dependencies),
            "",
        ]

    if skill.usage_example:
        body_lines += [
            "## Usage example",
            "",
            "```",
            skill.usage_example.strip(),
            "```",
            "",
        ]

    body_lines += [
        "## When to invoke",
        "",
        f"Use this skill when {skill.description.strip().rstrip('.')} -- "
        f"effort to integrate is **{skill.effort}**.",
        "",
    ]
    return "\n".join(body_lines)


def render_mcp_build_prompt(skill: ExtractableSkill, source_repo: str) -> str:
    """Render a prompt the user can paste into Claude Code to scaffold an MCP server."""
    safe = _safe_name(skill.name)
    deps = ", ".join(skill.dependencies) if skill.dependencies else "(infer from source)"
    files = "\n".join(f"  - {p}" for p in skill.source_files) or "  (none listed -- inspect the repo)"
    sigs = "\n".join(
        f"  - `{s.name}{s.args}` -- {s.summary}"
        for s in skill.suggested_tool_signatures
    ) or "  (design your own based on the rationale below)"

    return f"""# MCP server build task: {skill.name}

You are building a Python MCP server that exposes this skill as one or more tools.

## Source repository
{source_repo}

## What this skill does
{skill.description}

## Why this is worth wrapping
{skill.rationale}

## Source files to read first
{files}

## Suggested tool signatures
{sigs}

## Dependencies (likely)
{deps}

## Build instructions

1. Create a new repo `{safe}-mcp` with this layout:
   ```
   {safe}-mcp/
     pyproject.toml
     {safe}_mcp/
       __init__.py
       server.py          # FastMCP server with the tool decorators
       core.py            # The extracted logic from the source files above
     README.md
   ```

2. Use `mcp` Python SDK with `FastMCP`. Each tool above gets a `@mcp.tool()` decorator.

3. Port the core logic from the source files listed above into `core.py`. Strip
   any framework-specific glue (Streamlit, FastAPI, etc.); keep the pure function.

4. In `server.py`, instantiate `FastMCP("{safe}")`, wrap each core function with
   `@mcp.tool()`, and run via `mcp.run()` at module exec.

5. Write a `README.md` covering: install, configure (any required env vars), and
   how to register the server with Claude Desktop / Claude Code via
   `claude_desktop_config.json`.

6. Add `pyproject.toml` with `mcp[cli]>=1.0` plus the dependencies listed above.

## Usage example from the original
{skill.usage_example or '(none provided)'}

## Effort estimate
{skill.effort}

When you finish, run the server locally with `python -m {safe}_mcp.server` and
verify the tools are discoverable via `mcp dev`.
"""


def render_pack_readme(pack: SkillPack, source_repo: str) -> str:
    """Top-level README for the downloaded zip explaining what's inside."""
    lines = [
        f"# Skill pack extracted from {source_repo}",
        "",
        f"Generated by PaperPilot. {len(pack.skills)} extractable skill(s) found.",
        "",
        "## What's in here",
        "",
        "Each subdirectory is one skill. Inside each you'll find:",
        "- `SKILL.md` -- drop into `~/.claude/skills/<name>/` to load as a Claude Skill",
        "- `mcp_build_prompt.md` -- paste into Claude Code to scaffold an MCP server",
        "",
        "## Skills",
        "",
    ]
    for s in pack.skills:
        lines.append(f"### `{_safe_name(s.name)}` ({s.kind}, effort: {s.effort})")
        lines.append("")
        lines.append(s.description)
        lines.append("")
    return "\n".join(lines)


def build_skill_pack_zip(pack: SkillPack, source_repo: str) -> bytes:
    """Bundle every skill's SKILL.md + mcp_build_prompt.md into one zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", render_pack_readme(pack, source_repo))
        for skill in pack.skills:
            safe = _safe_name(skill.name)
            zf.writestr(f"{safe}/SKILL.md", render_skill_md(skill, source_repo))
            zf.writestr(
                f"{safe}/mcp_build_prompt.md",
                render_mcp_build_prompt(skill, source_repo),
            )
    return buf.getvalue()
