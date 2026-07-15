"""Draft one outreach message per channel with a direct LLM call.

Outreach generation used to route through Senso, which meant the surface
returned an error card for anyone without a Senso account -- that is, almost
everyone who clones this repo. The content-type templates Senso was being handed
are all the shaping a model needs, so we hand them to the model ourselves.

Senso remains supported as an optional enhancement (see orchestrator), but it is
no longer a precondition for getting a draft.
"""

from __future__ import annotations

from paperpilot.gateway import DEFAULTS, get_client
from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS

_SYSTEM_PROMPT = (
    "You are a writing assistant drafting professional outreach on behalf of "
    "the author described in the context. Write in the author's voice, in the "
    "first person. Be specific and concrete: reference the author's actual work "
    "rather than making generic claims. Never invent achievements, publications, "
    "affiliations, or metrics that are not present in the context. Output only "
    "the message itself, with no preamble and no commentary."
)


def _build_prompt(channel: str, full_context: str) -> str:
    """Compose the user prompt from the channel's template and writing rules."""
    config = CONTENT_TYPE_CONFIGS.get(channel, {})
    template = config.get("template", "")
    rules = config.get("writing_rules", [])
    rules_block = "\n".join(f"- {rule}" for rule in rules)
    return (
        f"Write the following:\n{template}\n\n"
        f"Rules you must follow:\n{rules_block}\n\n"
        f"{full_context}"
    )


def draft_channel(channel: str, full_context: str) -> str:
    """Return markdown for one outreach channel. Raises on model failure."""
    client = get_client()
    resp = client.chat.completions.create(
        model=DEFAULTS["draft"],
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(channel, full_context)},
        ],
        max_tokens=900,
        temperature=0.6,
    )
    return resp.choices[0].message.content or ""
