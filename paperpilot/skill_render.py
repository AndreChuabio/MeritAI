"""Render a PluginPack into a real Claude Code plugin directory zip.

Output layout matches the Claude Code plugin discovery convention:

  <plugin_name>/
    plugin.json                         # manifest
    README.md                           # human-readable overview
    skills/
      <skill_name>/SKILL.md             # frontmatter + body
    commands/
      <command_name>.md                 # slash command body
    agents/
      <agent_name>.md                   # frontmatter + system prompt
    hooks/
      hooks.json                        # hook config Claude Code reads
      <hook_name>.sh                    # the actual shell script(s)
    mcps/
      <mcp_name>/build_prompt.md        # not auto-installable; prompt to scaffold
      <mcp_name>/README.md

No LLM calls. Pure templating.
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from paperpilot.skill_extract import (
    AgentSpec,
    CommandSpec,
    HookSpec,
    MCPSpec,
    PluginPack,
    SkillSpec,
)


_KEBAB_RE = re.compile(r"[^a-z0-9-]+")
_SNAKE_RE = re.compile(r"[^a-z0-9_]+")


def _safe_kebab(name: str) -> str:
    s = name.strip().lower().replace("_", "-").replace(" ", "-")
    s = _KEBAB_RE.sub("", s)
    return s.strip("-") or "unnamed"


def _safe_snake(name: str) -> str:
    s = name.strip().lower().replace("-", "_").replace(" ", "_")
    s = _SNAKE_RE.sub("", s)
    return s or "unnamed"


def render_skill_md(skill: SkillSpec, source_repo: str) -> str:
    desc = skill.description.replace("\n", " ").strip()
    lines = [
        "---",
        f"name: {_safe_snake(skill.name)}",
        f"description: {desc}",
        "metadata:",
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
        skill.rationale.strip() or "(no rationale provided)",
        "",
    ]
    if skill.source_files:
        lines += ["## Source files in the original repo", ""]
        lines += [f"- `{p}`" for p in skill.source_files]
        lines += [""]
    if skill.key_functions:
        lines += ["## Key functions / classes", ""]
        lines += [f"- `{fn}`" for fn in skill.key_functions]
        lines += [""]
    if skill.usage_example:
        lines += ["## Usage example", "", "```", skill.usage_example.strip(), "```", ""]
    return "\n".join(lines)


def render_command_md(cmd: CommandSpec) -> str:
    fm = ["---", f"description: {cmd.description.strip()}"]
    if cmd.argument_hint:
        fm.append(f"argument-hint: {cmd.argument_hint}")
    fm += ["---", ""]
    return "\n".join(fm) + cmd.body.strip() + "\n"


def render_agent_md(agent: AgentSpec) -> str:
    fm = [
        "---",
        f"name: {_safe_kebab(agent.name)}",
        f"description: {agent.description.strip()}",
    ]
    if agent.tools:
        fm.append(f"tools: {', '.join(agent.tools)}")
    fm += ["---", ""]
    return "\n".join(fm) + agent.system_prompt.strip() + "\n"


def render_hooks_json(hooks: list[HookSpec]) -> str:
    """Build the hooks.json config Claude Code reads at plugin load."""
    grouped: dict[str, list[dict]] = {}
    for h in hooks:
        entry = {
            "type": "command",
            "command": f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{_safe_snake(h.name)}.sh",
        }
        bucket = {
            "matcher": h.matcher or "*",
            "hooks": [entry],
        }
        grouped.setdefault(h.event, []).append(bucket)
    return json.dumps({"hooks": grouped}, indent=2)


def render_hook_script(hook: HookSpec) -> str:
    script = hook.shell_script.strip()
    if not script.startswith("#!"):
        script = "#!/bin/bash\n" + script
    return script + "\n"


def render_mcp_build_prompt(mcp: MCPSpec, source_repo: str) -> str:
    deps = ", ".join(mcp.dependencies) if mcp.dependencies else "(infer from source)"
    files = "\n".join(f"  - {p}" for p in mcp.source_files) or "  (inspect the source repo)"
    sigs = "\n".join(
        f"  - `{s.name}{s.args}` -- {s.summary}" for s in mcp.suggested_tools
    ) or "  (design your own based on the rationale below)"
    safe = _safe_snake(mcp.name)
    return f"""# MCP server build task: {mcp.name}

You are building a Python MCP server that exposes this skill as one or more tools.

## Source repository
{source_repo}

## What this server does
{mcp.description}

## Why this is worth wrapping
{mcp.rationale}

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
       server.py          # FastMCP server with tool decorators
       core.py            # extracted logic from the source files above
     README.md
   ```
2. Use the `mcp` Python SDK with `FastMCP`. Each tool above gets a `@mcp.tool()` decorator.
3. Port the core logic from the source files into `core.py`. Strip framework-specific glue.
4. In `server.py`, instantiate `FastMCP("{safe}")`, wrap each function with `@mcp.tool()`, and run via `mcp.run()`.
5. README covers install, env vars, and Claude Desktop / Claude Code registration via `claude_desktop_config.json`.
6. `pyproject.toml` needs `mcp[cli]>=1.0` plus the dependencies listed above.

When done, `python -m {safe}_mcp.server` should run; verify tools are discoverable via `mcp dev`.
"""


def render_plugin_manifest(pack: PluginPack, source_repo: str) -> str:
    return json.dumps(
        {
            "name": _safe_kebab(pack.plugin_name),
            "version": "0.1.0",
            "description": pack.plugin_description,
            "source_repo": source_repo,
            "generated_by": "Merit",
            "contents": {
                "skills": [_safe_snake(s.name) for s in pack.skills],
                "commands": [_safe_kebab(c.name) for c in pack.commands],
                "agents": [_safe_kebab(a.name) for a in pack.agents],
                "hooks": [_safe_snake(h.name) for h in pack.hooks],
                "mcps": [_safe_snake(m.name) for m in pack.mcps],
            },
        },
        indent=2,
    )


def render_plugin_readme(pack: PluginPack, source_repo: str) -> str:
    lines = [
        f"# {pack.plugin_name}",
        "",
        pack.plugin_description or "(no description)",
        "",
        f"**Source repo:** {source_repo}",
        "**Generated by:** Merit",
        "",
        "## Install",
        "",
        "```bash",
        "# Unzip, then move into your Claude plugins dir:",
        f"mv {_safe_kebab(pack.plugin_name)} ~/.claude/plugins/",
        "```",
        "",
        "Restart Claude Code; the plugin discovers automatically.",
        "",
        "## Contents",
        "",
    ]
    if pack.skills:
        lines += ["### Skills", ""]
        lines += [f"- **{s.name}** -- {s.description}" for s in pack.skills]
        lines += [""]
    if pack.commands:
        lines += ["### Commands", ""]
        lines += [f"- `/{_safe_kebab(c.name)}` -- {c.description}" for c in pack.commands]
        lines += [""]
    if pack.agents:
        lines += ["### Subagents", ""]
        lines += [f"- **{_safe_kebab(a.name)}** -- {a.description}" for a in pack.agents]
        lines += [""]
    if pack.hooks:
        lines += ["### Hooks", ""]
        lines += [f"- **{h.event}** / `{h.name}` -- {h.description}" for h in pack.hooks]
        lines += [""]
    if pack.mcps:
        lines += ["### MCP servers (build prompts)", ""]
        lines += [f"- **{m.name}** -- {m.description}" for m in pack.mcps]
        lines += [""]
    lines += [
        "## What's *not* included",
        "",
        "MCP servers in `mcps/` are NOT auto-scaffolded. Each folder contains a",
        "ready-to-paste prompt for Claude Code that scaffolds the server in a",
        "fresh session. Open `mcps/<name>/build_prompt.md` and run it.",
        "",
    ]
    return "\n".join(lines)


def build_plugin_zip(pack: PluginPack, source_repo: str) -> bytes:
    """Bundle the full plugin layout into a single downloadable zip."""
    buf = io.BytesIO()
    root = _safe_kebab(pack.plugin_name)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/plugin.json", render_plugin_manifest(pack, source_repo))
        zf.writestr(f"{root}/README.md", render_plugin_readme(pack, source_repo))

        for skill in pack.skills:
            safe = _safe_snake(skill.name)
            zf.writestr(
                f"{root}/skills/{safe}/SKILL.md", render_skill_md(skill, source_repo)
            )

        for cmd in pack.commands:
            safe = _safe_kebab(cmd.name)
            zf.writestr(f"{root}/commands/{safe}.md", render_command_md(cmd))

        for agent in pack.agents:
            safe = _safe_kebab(agent.name)
            zf.writestr(f"{root}/agents/{safe}.md", render_agent_md(agent))

        if pack.hooks:
            zf.writestr(f"{root}/hooks/hooks.json", render_hooks_json(pack.hooks))
            for hook in pack.hooks:
                safe = _safe_snake(hook.name)
                info = zipfile.ZipInfo(f"{root}/hooks/{safe}.sh")
                info.compress_type = zipfile.ZIP_DEFLATED
                # Unix exec bit so users don't need chmod +x after unzipping.
                info.external_attr = 0o755 << 16
                zf.writestr(info, render_hook_script(hook))

        for mcp in pack.mcps:
            safe = _safe_snake(mcp.name)
            zf.writestr(
                f"{root}/mcps/{safe}/build_prompt.md",
                render_mcp_build_prompt(mcp, source_repo),
            )
            zf.writestr(
                f"{root}/mcps/{safe}/README.md",
                f"# {mcp.name}\n\n{mcp.description}\n\n"
                "See `build_prompt.md` and paste into Claude Code to scaffold.\n",
            )
    return buf.getvalue()
