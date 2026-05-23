"""Gemini 1M-context repo ingestion → structured research summary.

Single Gateway call. The model is asked to produce JSON matching
`ResearchSummary` schema below; we validate via Pydantic and surface
structured output to the rest of the pipeline.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from paperpilot import trace
from paperpilot.github_ingest import RepoBundle, render_bundle
from paperpilot.gateway import DEFAULTS, get_client


SYSTEM_PROMPT = """You are a research scientist reviewing a GitHub repository to extract a paper-shaped summary.

You will receive a repository bundle (README + ranked source files). Read the whole bundle and produce a JSON object with these fields:

- problem: the research problem or pain this work addresses (1-2 sentences)
- contribution: the specific novel contribution -- what is new here (1-2 sentences)
- method: how the work approaches the problem -- techniques, architecture, datasets (2-4 sentences)
- results: empirical results, benchmarks, or qualitative outcomes mentioned in the code/docs (1-3 sentences)
- limitations: known limitations, scope cuts, or future work the code/docs admit to (1-3 sentences)
- keywords: 4-8 short keywords/topic tags useful for venue matching
- venue_hints: 1-3 venues this work would plausibly target (workshop or conference names if obvious)

Be specific. Cite filenames or function names in your reasoning when possible. If the repo is too small or unrelated to research, say so honestly in `limitations`.

Output ONLY valid JSON. No prose before or after."""


class ResearchSummary(BaseModel):
    problem: str
    contribution: str
    method: str
    results: str
    limitations: str
    keywords: list[str] = Field(default_factory=list)
    venue_hints: list[str] = Field(default_factory=list)


def summarize_repo(bundle: RepoBundle, session_id: str) -> ResearchSummary:
    """Call Gemini through the Gateway to summarize the repo."""
    rendered = render_bundle(bundle)
    model = DEFAULTS["ingest"]

    with trace.step(
        session_id,
        "ingest.gemini",
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
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.2,
        )
        raw = completion.choices[0].message.content or "{}"
        ctx["finish_reason"] = completion.choices[0].finish_reason
        if completion.usage:
            ctx["tokens_in"] = completion.usage.prompt_tokens
            ctx["tokens_out"] = completion.usage.completion_tokens
        try:
            parsed: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            ctx["error"] = f"json_parse_failed: {exc!s}"
            ctx["raw_preview"] = raw[:400]
            raise
        summary = ResearchSummary.model_validate(parsed)
        ctx["summary_keys"] = list(parsed.keys())

    return summary
