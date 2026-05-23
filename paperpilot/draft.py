"""Paper drafting with citation-gated related work.

Section-by-section streaming via Claude through the Gateway. Related work
gets the citation gate: model sees only approved arxiv candidate IDs and
can only cite those. Post-hoc regex strip removes any unsanctioned IDs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Generator, Iterable

from paperpilot import trace
from paperpilot.arxiv_lookup import (
    PaperMeta,
    candidates_from_clickhouse,
    lookup_paper,
)
from paperpilot.cfp_match import VenueMatch
from paperpilot.gateway import DEFAULTS, get_client
from paperpilot.llm_ingest import ResearchSummary


SECTIONS = ("abstract", "intro", "related", "method")


CITATION_RE = re.compile(r"\[arxiv:([^\]]+)\]")


@dataclass
class DraftSection:
    name: str
    text: str
    citations: list[PaperMeta] = field(default_factory=list)
    stripped_ids: list[str] = field(default_factory=list)


def _section_prompt(
    section: str,
    summary: ResearchSummary,
    venue: VenueMatch,
    candidates: Iterable[PaperMeta] | None = None,
) -> tuple[str, str]:
    """Build (system, user) prompt for a section."""
    common_user = (
        f"Repository research summary:\n"
        f"- Problem: {summary.problem}\n"
        f"- Contribution: {summary.contribution}\n"
        f"- Method: {summary.method}\n"
        f"- Results: {summary.results}\n"
        f"- Limitations: {summary.limitations}\n"
        f"- Keywords: {', '.join(summary.keywords)}\n\n"
        f"Target venue: {venue.name} ({venue.scope})\n"
    )

    if section == "abstract":
        sys = (
            "You write tight, academically-toned paper abstracts (150-200 words). "
            "Single paragraph. No citations. No headers. Match the venue's tone."
        )
        return sys, common_user + "\nWrite the abstract."

    if section == "intro":
        sys = (
            "You write academic paper introductions (~350 words). Three paragraphs: "
            "problem motivation, limitations of prior work in general terms, and a "
            "preview of the contribution. Do not cite specific papers here -- save "
            "those for the related-work section. Match the venue's tone."
        )
        return sys, common_user + "\nWrite the introduction."

    if section == "related":
        cand_list = list(candidates or [])
        cand_block = "\n".join(
            f"- [arxiv:{c.id}] {c.title} ({c.year}). {c.abstract[:200]}..."
            for c in cand_list
        )
        sys = (
            "You write related-work sections for ML/CS papers. STRICT RULES:\n"
            "1. You may ONLY cite papers from the approved candidate list below.\n"
            "2. Use inline markers like [arxiv:2401.12345] -- nothing else counts.\n"
            "3. Cite at least 4 candidates; do not invent IDs.\n"
            "4. Group citations by theme. ~300 words. Match the venue's tone."
        )
        user = (
            common_user
            + "\nApproved candidates (cite ONLY these):\n"
            + cand_block
            + "\n\nWrite the related-work section."
        )
        return sys, user

    if section == "method":
        sys = (
            "You write the opening paragraph of a paper's method section (~200 "
            "words). Describe the high-level approach grounded in the repository "
            "summary -- no implementation details that aren't supported. No "
            "citations. Match the venue's tone."
        )
        return sys, common_user + "\nWrite the opening paragraph of the method section."

    raise ValueError(f"Unknown section: {section}")


def _strip_unapproved(text: str, approved_ids: set[str]) -> tuple[str, list[str]]:
    """Remove any [arxiv:id] markers not in approved_ids; return cleaned text + dropped ids."""
    dropped: list[str] = []

    def sub(match: re.Match[str]) -> str:
        aid = match.group(1).strip()
        if aid in approved_ids:
            return f"[arxiv:{aid}]"
        dropped.append(aid)
        return ""

    return CITATION_RE.sub(sub, text), dropped


def draft_section(
    section: str,
    summary: ResearchSummary,
    venue: VenueMatch,
    session_id: str,
    candidates: list[PaperMeta] | None = None,
) -> Generator[str, None, DraftSection]:
    """Stream a paper section, yielding deltas as they arrive."""
    sys_prompt, user_prompt = _section_prompt(section, summary, venue, candidates)
    model = DEFAULTS["draft"]

    with trace.step(
        session_id,
        f"draft.{section}",
        model=model,
        venue=venue.name,
        candidate_count=len(candidates) if candidates else 0,
    ) as ctx:
        client = get_client()
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            max_tokens=900,
            temperature=0.5,
        )
        chunks: list[str] = []
        for event in stream:
            delta = event.choices[0].delta.content if event.choices else None
            if delta:
                chunks.append(delta)
                yield delta
        full_text = "".join(chunks)
        ctx["chars"] = len(full_text)

    citations: list[PaperMeta] = []
    stripped: list[str] = []
    if section == "related" and candidates is not None:
        approved = {c.id for c in candidates}
        full_text, stripped = _strip_unapproved(full_text, approved)
        for aid in set(CITATION_RE.findall(full_text)):
            meta = lookup_paper(aid)
            if meta is not None:
                citations.append(meta)

    return DraftSection(
        name=section, text=full_text, citations=citations, stripped_ids=stripped
    )


def draft_paper(
    summary: ResearchSummary,
    venue: VenueMatch,
    session_id: str,
) -> Generator[tuple[str, str], None, dict[str, DraftSection]]:
    """Stream all sections in order. Yields (section_name, delta) tuples.

    Returns the assembled dict[section_name -> DraftSection] at the end.
    """
    summary_text = (
        f"{summary.problem} {summary.contribution} {summary.method} "
        f"Keywords: {', '.join(summary.keywords)}"
    )
    candidates = candidates_from_clickhouse(summary_text, session_id, limit=10)
    out: dict[str, DraftSection] = {}
    for section in SECTIONS:
        gen = draft_section(
            section,
            summary,
            venue,
            session_id,
            candidates if section == "related" else None,
        )
        try:
            while True:
                delta = next(gen)
                yield section, delta
        except StopIteration as stop:
            out[section] = stop.value
    return out
