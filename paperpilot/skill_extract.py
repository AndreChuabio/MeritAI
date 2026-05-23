"""Skill extraction: turn a GitHub repo into publishable Claude Skills + MCP build prompts.

A single Gateway LLM call inspects the same `RepoBundle` we already fetched
for paper summarization, and returns a structured list of reusable units --
each one ready to be dropped into ~/.claude/skills/<name>/ as a SKILL.md, OR
handed to Claude Code with a "build me an MCP server for this" prompt.

This sidesteps the hard problem of auto-generating a working MCP server
scaffold (server.py + tool decorators + packaging) by instead generating a
high-quality build prompt that lets the user finish in their own Claude
Code session -- honest, low-risk, and matches the real ecosystem flow.
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


SYSTEM_PROMPT = """You are a senior engineer reviewing a GitHub repository to find reusable, publishable units of capability inside it.

You will receive a repository bundle (README + ranked source files). Identify between 2 and 5 distinct "extractable skills" -- self-contained pieces of functionality that could be lifted out and republished as either:
  - A Claude Skill (a SKILL.md + supporting files, loaded into Claude Code or claude.ai)
  - An MCP server tool (a function exposed to any MCP-aware LLM client)
  - Or both.

Look especially for:
  - Agent loops, planners, or tool-calling glue
  - Retrieval / search primitives (embedding search, ranking, filtering)
  - Domain-specific extractors, parsers, or rankers
  - Citation / fact-grounding / hallucination guards
  - Workflow orchestrators (multi-step pipelines that take input X -> useful artifact Y)
  - Data shapers (converters, normalizers, dedupers)

Output a JSON object matching this schema EXACTLY:

{
  "skills": [
    {
      "name": "short_snake_case_name",
      "kind": "claude_skill" | "mcp_tool" | "both",
      "description": "One sentence -- what this skill does, written so a future user knows when to invoke it.",
      "rationale": "Why this is worth extracting: what makes it reusable, what problem it solves outside the original repo.",
      "source_files": ["paths/relative/to/repo.py", ...],
      "key_functions": ["function_or_class_names_that_implement_the_capability"],
      "suggested_tool_signatures": [
        {"name": "tool_name", "args": "(arg1: type, arg2: type) -> ReturnType", "summary": "what it does"}
      ],
      "dependencies": ["any-python-package-or-external-service-required"],
      "effort": "small" | "medium" | "large",
      "usage_example": "A short prose example or code snippet showing how a downstream user would invoke this skill."
    }
  ]
}

Rules:
- Be HONEST. If the repo has no extractable skills (e.g. it's a toy script or just config), return {"skills": []}.
- Prefer specificity over volume: 2 sharp skills beats 5 mushy ones.
- `name` must be a valid Python identifier (snake_case, no spaces, no hyphens).
- `source_files` must reference real paths from the bundle. Do not invent paths.
- `effort` is your gut estimate of how long it would take a competent engineer to extract this cleanly: small=under 1hr, medium=half-day, large=multi-day.

Output ONLY valid JSON. No prose before or after."""


class ToolSignature(BaseModel):
    name: str
    args: str = ""
    summary: str = ""


class ExtractableSkill(BaseModel):
    name: str
    kind: str  # "claude_skill" | "mcp_tool" | "both"
    description: str
    rationale: str
    source_files: list[str] = Field(default_factory=list)
    key_functions: list[str] = Field(default_factory=list)
    suggested_tool_signatures: list[ToolSignature] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    effort: str = "medium"
    usage_example: str = ""


class SkillPack(BaseModel):
    skills: list[ExtractableSkill] = Field(default_factory=list)


def extract_skills(bundle: RepoBundle, session_id: str) -> SkillPack:
    """Single LLM call -> structured SkillPack. Traced through trace.step."""
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
            max_tokens=8000,
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
        pack = SkillPack.model_validate(parsed)
        ctx["skill_count"] = len(pack.skills)
        ctx["skill_names"] = [s.name for s in pack.skills]

    return pack
