"""Claude Code plugin extraction.

A single Gateway LLM call inspects the same `RepoBundle` we already fetched
for paper summarization, and returns a structured `PluginPack` describing a
publishable Claude Code plugin: skills, slash commands, subagents, hooks,
and MCP server suggestions.

The rendering layer (`skill_render.py`) turns the PluginPack into a real
on-disk plugin layout (skills/, commands/, agents/, hooks/, plugin.json)
zipped for download. Users drop the unzipped folder into
`~/.claude/plugins/<name>/` and Claude Code picks it up.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from paperpilot import trace
from paperpilot.gateway import DEFAULTS, get_client
from paperpilot.github_ingest import RepoBundle, render_bundle


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


SYSTEM_PROMPT = """You are a senior engineer turning a GitHub repository into a publishable Claude Code plugin.

You will receive a repository bundle (README + ranked source files). Identify reusable units inside the repo and propose a Claude Code plugin that bundles them. A plugin can contain ANY of:

- **skills**: SKILL.md files invoked when the user is doing a relevant task. Best for codified workflows or domain knowledge.
- **commands**: slash commands the user explicitly invokes (like /review or /test). Best for discrete on-demand actions.
- **agents**: subagents Claude can delegate to. Best for specialized roles (e.g. "data-pipeline-debugger").
- **hooks**: shell scripts triggered on Claude Code lifecycle events (PreToolUse, PostToolUse, Stop, UserPromptSubmit, SessionStart). Best for guardrails, logging, or auto-formatting.
- **mcps**: suggested MCP servers to expose the repo's capabilities as tools to any MCP-aware client.

Be honest and specific. If the repo has only 1-2 extractable pieces, return only those -- DO NOT pad. If a category has nothing to offer, return an empty list for it.

Look especially for:
- Agent loops, planners, tool-calling glue --> agents or commands
- Retrieval / search primitives, embedding pipelines --> mcps (most reusable)
- Domain-specific extractors, parsers, rankers --> skills or commands
- Citation / fact-grounding / hallucination guards --> skills or hooks (PostToolUse)
- Workflow orchestrators (multi-step pipelines) --> commands
- Quality gates, validation steps --> hooks (PreToolUse or PostToolUse)
- Data shapers, normalizers --> mcps

Output a JSON object matching this schema EXACTLY:

{
  "plugin_name": "short-kebab-case-plugin-name",
  "plugin_description": "One-sentence pitch: what the plugin gives a user.",
  "source_files_overview": ["paths/that/were/key/to/this/analysis.py", ...],
  "skills": [
    {
      "name": "snake_case_name",
      "description": "One sentence describing what it does, written so a future user knows when to invoke it.",
      "rationale": "Why this is worth extracting; what problem it solves outside the original repo.",
      "source_files": ["paths/relative/to/repo.py", ...],
      "key_functions": ["function_or_class_names"],
      "usage_example": "Prose or code snippet showing invocation.",
      "effort": "small" | "medium" | "large"
    }
  ],
  "commands": [
    {
      "name": "kebab-case-command-name",
      "description": "What /command-name does (one sentence).",
      "body": "Full markdown body of the command -- written as instructions to Claude on what to do when this command is invoked. Reference $ARGUMENTS if it takes args.",
      "argument_hint": "<repo-url> or null"
    }
  ],
  "agents": [
    {
      "name": "kebab-case-agent-name",
      "description": "One sentence on the agent's specialty.",
      "tools": ["Read", "Grep", "Bash"],
      "system_prompt": "Multi-paragraph system prompt for the subagent. Should be specific and role-driven, not generic."
    }
  ],
  "hooks": [
    {
      "event": "PreToolUse" | "PostToolUse" | "Stop" | "UserPromptSubmit" | "SessionStart",
      "matcher": "Bash" | "Edit" | "Write" | "*" | null,
      "name": "snake_case_hook_name",
      "description": "One sentence on what this hook enforces or logs.",
      "shell_script": "#!/bin/bash\\n# Full hook body. Reads JSON from stdin, exits non-zero to block.\\n..."
    }
  ],
  "mcps": [
    {
      "name": "kebab-case-mcp-server-name",
      "description": "One sentence on the MCP server's purpose.",
      "rationale": "Why this is the right surface for these capabilities.",
      "source_files": ["paths/relative/to/repo.py", ...],
      "suggested_tools": [
        {"name": "tool_name", "args": "(arg1: type, arg2: type) -> ReturnType", "summary": "what it does"}
      ],
      "dependencies": ["python-package-or-service-required"]
    }
  ]
}

Hard rules:
- All `name` fields must be valid identifiers (snake_case for skills/agents/hooks/mcps, kebab-case for commands/plugin_name).
- `source_files` must reference real paths from the bundle. Do not invent.
- Empty lists are OK for any category. Better to omit than to fabricate.
- Hook `shell_script` must be syntactically valid bash. Reads from stdin (Claude Code passes hook input as JSON). Exit 0 to allow, non-zero to block (for PreToolUse).
- A good plugin has between 1 and 8 total artifacts across all categories. Quality > quantity.

Output ONLY valid JSON. No prose before or after."""


class SkillSpec(BaseModel):
    name: str
    description: str
    rationale: str = ""
    source_files: list[str] = Field(default_factory=list)
    key_functions: list[str] = Field(default_factory=list)
    usage_example: str = ""
    effort: str = "medium"


class CommandSpec(BaseModel):
    name: str
    description: str
    body: str
    argument_hint: str | None = None


class AgentSpec(BaseModel):
    name: str
    description: str
    tools: list[str] = Field(default_factory=list)
    system_prompt: str


class HookSpec(BaseModel):
    event: str
    matcher: str | None = None
    name: str
    description: str
    shell_script: str


class MCPToolSig(BaseModel):
    name: str
    args: str = ""
    summary: str = ""


class MCPSpec(BaseModel):
    name: str
    description: str
    rationale: str = ""
    source_files: list[str] = Field(default_factory=list)
    suggested_tools: list[MCPToolSig] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class PluginPack(BaseModel):
    plugin_name: str = "extracted-plugin"
    plugin_description: str = ""
    source_files_overview: list[str] = Field(default_factory=list)
    skills: list[SkillSpec] = Field(default_factory=list)
    commands: list[CommandSpec] = Field(default_factory=list)
    agents: list[AgentSpec] = Field(default_factory=list)
    hooks: list[HookSpec] = Field(default_factory=list)
    mcps: list[MCPSpec] = Field(default_factory=list)

    @property
    def total_artifacts(self) -> int:
        return (
            len(self.skills)
            + len(self.commands)
            + len(self.agents)
            + len(self.hooks)
            + len(self.mcps)
        )


def extract_plugin(bundle: RepoBundle, session_id: str) -> PluginPack:
    """Single LLM call -> structured PluginPack. Traced through trace.step."""
    rendered = render_bundle(bundle)
    model = DEFAULTS["ingest"]  # Reuse Gemini -- long context, cheap, good at structured extraction.

    with trace.step(
        session_id,
        "skill.extract",
        repo=f"{bundle.owner}/{bundle.name}",
        files=bundle.file_count,
        repo_tokens=bundle.total_tokens,
        model=model,
    ) as ctx:
        client = get_client()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": rendered},
            ],
            max_tokens=12000,
            temperature=0.3,
        )
        raw = completion.choices[0].message.content or "{}"
        ctx["finish_reason"] = completion.choices[0].finish_reason
        if completion.usage:
            ctx["tokens_in"] = completion.usage.prompt_tokens
            ctx["tokens_out"] = completion.usage.completion_tokens
            gw_cost = getattr(completion.usage, "cost", None)
            if gw_cost is not None:
                ctx["cost_usd"] = gw_cost
                ctx["cost_source"] = "gateway"
            else:
                from paperpilot.draft import _estimate_cost
                ctx["cost_usd"] = _estimate_cost(
                    model, ctx["tokens_in"], ctx["tokens_out"]
                )
                ctx["cost_source"] = "estimated"
        try:
            parsed: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            match = _JSON_BLOCK_RE.search(raw)
            if match is None:
                ctx["error"] = "json_extract_failed"
                ctx["raw_preview"] = raw[:400]
                raise
            parsed = json.loads(match.group(0))
            ctx["json_recovered"] = True
        pack = PluginPack.model_validate(parsed)
        ctx["plugin_name"] = pack.plugin_name
        ctx["counts"] = {
            "skills": len(pack.skills),
            "commands": len(pack.commands),
            "agents": len(pack.agents),
            "hooks": len(pack.hooks),
            "mcps": len(pack.mcps),
        }

    return pack
