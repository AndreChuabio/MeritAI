"""Per-criterion O-1A narrative drafter.

For each of the eight USCIS O-1A criteria, this module produces an
attorney-quality ~200-word petition narrative paragraph by combining:

  * The user's declared evidence (`o1_evidence` rows via
    `paperpilot.outreach.evidence.list_evidence`).
  * Auto-derived signals where available (Google Scholar metrics for the
    publication-oriented criteria; declared evidence only for the rest).
  * Light user-profile context (name / title / about) when looked up by
    user_id in the `user_profile` table.

LLM access goes through the Vercel AI Gateway (`paperpilot.gateway`) and
streams via the OpenAI-compatible chat completion API, identical to the
pattern in `paperpilot.draft`. Every call is wrapped in
`paperpilot.trace.step` so it lands in Datadog LLM Obs alongside the
paper drafting steps.

Failures from the Scholar fetcher are caught and downgraded to a
"Scholar signal: not available" line in the prompt; LLM failures are
re-raised as `RuntimeError` with context (no silent fallback).
"""

from __future__ import annotations

import logging
from typing import Iterator, Optional

from paperpilot import trace
from paperpilot.clickhouse_client import get_client as get_ch_client
from paperpilot.gateway import DEFAULTS, get_client
from paperpilot.outreach import scholar
from paperpilot.outreach.evidence import (
    CRITERION_KEYS,
    EvidenceItem,
    USCIS_O1A_CRITERIA,
    list_evidence,
)
from paperpilot.outreach.log import UserProfile

logger = logging.getLogger(__name__)


# Criteria where Scholar metrics meaningfully reinforce the narrative.
# All other criteria rely on declared evidence + user context alone.
_SCHOLAR_RELEVANT_CRITERIA: frozenset[str] = frozenset(
    {"scholarly_articles", "original_contributions"}
)


_CRITERION_DEFINITIONS: dict[str, str] = dict(USCIS_O1A_CRITERIA)


_SYSTEM_PROMPT = (
    "You draft USCIS O-1A petition narratives for an immigration attorney. "
    "Write one self-contained paragraph of approximately 200 words for the "
    "single criterion provided. Use formal third-person register, refer to "
    "the beneficiary by surname or pronouns once introduced, and ground "
    "every assertion in the declared evidence supplied. Do not hedge with "
    "phrases such as 'may', 'might', or 'arguably'. Do not invent facts, "
    "publications, dates, employers, or awards that are not present in the "
    "supplied evidence. Do not use emojis, exclamation marks, bullet "
    "points, headers, or markdown formatting. Output prose only."
)


def _find_user_profile_by_id(user_id: str) -> Optional[UserProfile]:
    """Look up the latest profile row for a user_id, or None.

    Lives here rather than in `outreach.log` because that module is owned
    by another agent during this P1 sprint; once that module exposes an
    equivalent by_id helper this private wrapper should be removed.
    """
    if not user_id:
        return None
    try:
        client = get_ch_client()
        result = client.query(
            "SELECT user_id, name, title, about, voice_tone, github_url, "
            "linkedin_url, scholar_url, site_url, resume_text "
            "FROM user_profile FINAL "
            "WHERE user_id = {u:String} "
            "ORDER BY updated_at DESC LIMIT 1",
            parameters={"u": user_id},
        )
    except Exception as exc:  # noqa: BLE001 -- profile is optional context
        logger.warning("user_profile lookup failed for user_id=%s: %s", user_id, exc)
        return None
    rows = result.result_rows
    if not rows:
        return None
    r = rows[0]
    return UserProfile(
        user_id=r[0], name=r[1], title=r[2], about=r[3],
        voice_tone=r[4], github_url=r[5], linkedin_url=r[6],
        scholar_url=r[7], site_url=r[8], resume_text=r[9],
    )


def _format_evidence_block(items: list[EvidenceItem]) -> str:
    """Render declared evidence items as a numbered list for the prompt."""
    if not items:
        return "Declared evidence: none on file."
    lines = ["Declared evidence (verbatim from the user):"]
    for idx, item in enumerate(items, start=1):
        date_str = item.evidence_date.isoformat() if item.evidence_date else "undated"
        url_str = item.evidence_url.strip() or "no URL provided"
        title = item.title.strip() or "(no title)"
        desc = item.description.strip() or "(no description)"
        lines.append(
            f"{idx}. {title} [{date_str}] -- {desc} (source: {url_str})"
        )
    return "\n".join(lines)


def _format_profile_block(profile: Optional[UserProfile]) -> str:
    """Render the beneficiary profile context block for the prompt."""
    if profile is None:
        return "Beneficiary profile: not on file; refer to the beneficiary generically."
    name = profile.name.strip() or "the beneficiary"
    title = profile.title.strip() or "unspecified role"
    about = profile.about.strip() or "no biographical summary provided"
    return (
        f"Beneficiary: {name}, {title}. "
        f"Background: {about}"
    )


def _format_scholar_block(
    profile: Optional[UserProfile],
    criterion: str,
) -> str:
    """Render auto-derived Scholar signal for publication-related criteria.

    Returns a short prompt block. Always returns a non-empty string so the
    LLM sees an explicit acknowledgement instead of a missing section.
    Failures from `scholar.fetch` are caught and downgraded.
    """
    if criterion not in _SCHOLAR_RELEVANT_CRITERIA:
        return "Auto-derived signal: not applicable to this criterion."
    scholar_url = (profile.scholar_url.strip() if profile else "") or None
    try:
        data = scholar.fetch(scholar_url)
    except Exception as exc:  # noqa: BLE001 -- non-critical signal
        logger.warning(
            "scholar.fetch failed for criterion=%s user=%s: %s",
            criterion,
            profile.user_id if profile else "<unknown>",
            exc,
        )
        return "Scholar signal: not available."
    paper_count = len(data.papers)
    return (
        "Scholar signal (auto-derived; cite only as supporting context, "
        f"not as a primary award): {paper_count} indexed publications, "
        f"{data.total_citations} total citations, h-index {data.h_index}."
    )


def _build_user_prompt(
    criterion: str,
    items: list[EvidenceItem],
    profile: Optional[UserProfile],
) -> str:
    """Assemble the user-message body for one criterion."""
    definition = _CRITERION_DEFINITIONS[criterion]
    sections = [
        f"USCIS O-1A criterion: {criterion}",
        f"Criterion definition: {definition}",
        "",
        _format_profile_block(profile),
        "",
        _format_evidence_block(items),
        "",
        _format_scholar_block(profile, criterion),
        "",
        (
            "Draft a single ~200-word paragraph that an immigration attorney "
            "could lift verbatim into a petition cover letter to argue that "
            "the beneficiary satisfies this criterion. Anchor every claim in "
            "the declared evidence above. If declared evidence is sparse, "
            "make the strongest accurate case the evidence supports rather "
            "than padding with generalities. Output the paragraph and "
            "nothing else."
        ),
    ]
    return "\n".join(sections)


def draft_criterion_narrative(
    user_id: str,
    criterion: str,
    session_id: Optional[str] = None,
) -> Iterator[str]:
    """Stream a ~200-word petition-quality narrative for one O-1A criterion.

    Loads the user's declared evidence for `criterion` via
    `paperpilot.outreach.evidence.list_evidence`, plus any auto-derived
    signals available for that criterion. Yields incremental string deltas
    suitable for `st.write_stream`.

    Raises ValueError if `criterion` is not in `CRITERION_KEYS`.
    Raises RuntimeError if the LLM call fails (no silent fallback).
    """
    if not user_id:
        raise ValueError("user_id is required")
    if criterion not in CRITERION_KEYS:
        raise ValueError(
            f"unknown criterion {criterion!r}; expected one of "
            f"{sorted(CRITERION_KEYS)}"
        )

    items = list_evidence(user_id, criterion=criterion)
    profile = _find_user_profile_by_id(user_id)
    user_prompt = _build_user_prompt(criterion, items, profile)
    model = DEFAULTS["draft"]

    # Use a deterministic placeholder session_id when the caller did not
    # supply one so trace.step never sees an empty string. The buffer is
    # in-process so this keeps narrative drafts inspectable in tests.
    sid = session_id or f"evidence_draft_{user_id}"

    with trace.step(
        sid,
        f"evidence_draft.{criterion}",
        model=model,
        user_id=user_id,
        criterion=criterion,
        declared_item_count=len(items),
        has_profile=profile is not None,
    ) as ctx:
        try:
            client = get_client()
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                stream_options={"include_usage": True},
                max_tokens=600,
                temperature=0.4,
            )
        except Exception as exc:  # noqa: BLE001 -- re-raise with context
            logger.exception(
                "LLM stream init failed for criterion=%s user=%s",
                criterion,
                user_id,
            )
            raise RuntimeError(
                f"evidence_draft LLM init failed for criterion={criterion!r}: {exc}"
            ) from exc

        chunks: list[str] = []
        final_usage = None
        try:
            for event in stream:
                if getattr(event, "usage", None):
                    final_usage = event.usage
                delta = event.choices[0].delta.content if event.choices else None
                if delta:
                    chunks.append(delta)
                    yield delta
        except Exception as exc:  # noqa: BLE001 -- re-raise with context
            logger.exception(
                "LLM stream consume failed for criterion=%s user=%s",
                criterion,
                user_id,
            )
            raise RuntimeError(
                f"evidence_draft LLM stream failed for criterion={criterion!r}: {exc}"
            ) from exc

        full_text = "".join(chunks)
        ctx["chars"] = len(full_text)
        if final_usage:
            ctx["tokens_in"] = final_usage.prompt_tokens
            ctx["tokens_out"] = final_usage.completion_tokens
            gw_cost = getattr(final_usage, "cost", None)
            if gw_cost is not None:
                ctx["cost_usd"] = gw_cost
                ctx["cost_source"] = "gateway"
            else:
                # Fall back to draft.py's estimator to keep the cost pill
                # populated. Import locally to avoid a top-level cycle on
                # paperpilot.draft (which pulls cfp_match + arxiv_lookup).
                from paperpilot.draft import _estimate_cost

                ctx["cost_usd"] = _estimate_cost(
                    model, final_usage.prompt_tokens, final_usage.completion_tokens
                )
                ctx["cost_source"] = "estimated"
        else:
            from paperpilot.draft import _estimate_cost, _tok_count

            t_in = _tok_count(_SYSTEM_PROMPT) + _tok_count(user_prompt)
            t_out = _tok_count(full_text)
            ctx["tokens_in"] = t_in
            ctx["tokens_out"] = t_out
            ctx["cost_usd"] = _estimate_cost(model, t_in, t_out)
            ctx["cost_source"] = "estimated"


def draft_all_narratives(
    user_id: str,
    session_id: Optional[str] = None,
) -> dict[str, str]:
    """Materialize all eight narratives sequentially.

    Returns a dict keyed by criterion -> finished narrative text (or empty
    string when the user has zero declared items for that criterion).
    Used by the PDF dossier export. Calls are sequential to stay under AI
    Gateway rate limits; PDF generation is not latency-sensitive.

    Raises RuntimeError if any LLM call fails, with the criterion in
    context (no silent skip).
    """
    if not user_id:
        raise ValueError("user_id is required")

    out: dict[str, str] = {}
    for key, _definition in USCIS_O1A_CRITERIA:
        items = list_evidence(user_id, criterion=key)
        if not items:
            out[key] = ""
            continue
        # Drain the streaming generator into a string. We deliberately
        # reuse draft_criterion_narrative so the same prompt, trace span,
        # and error handling apply uniformly across both entry points.
        try:
            chunks: list[str] = []
            for delta in draft_criterion_narrative(
                user_id=user_id,
                criterion=key,
                session_id=session_id,
            ):
                chunks.append(delta)
            out[key] = "".join(chunks)
        except RuntimeError:
            # Already wrapped with criterion context; let it bubble up so
            # the PDF caller can surface which criterion failed.
            raise
        except Exception as exc:  # noqa: BLE001 -- guarantee wrap
            raise RuntimeError(
                f"evidence_draft failed for criterion={key!r}: {exc}"
            ) from exc
    return out
