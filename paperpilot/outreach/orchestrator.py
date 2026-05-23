"""Outreach orchestrator: purpose -> Senso draft cards.

Wraps every Senso call in `paperpilot.trace.step` so the existing Lapdog
pipeline captures each step into Datadog. Errors on one channel do not
cancel the others — the failing card carries an `error` string for the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperpilot import trace
from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS
from paperpilot.outreach.purpose import Purpose, channels_for
from paperpilot.outreach.senso import Senso


@dataclass
class DraftCard:
    channel: str
    content_type_id: str
    sample_job_id: str
    markdown: str
    draft_id: str = ""
    error: str | None = None


def _build_context(purpose: Purpose, user_context: str) -> str:
    purpose_blurbs = {
        Purpose.VISA: (
            "Audience: conference organizers, journal editors, and selection "
            "committees evaluating extraordinary-ability candidates."
        ),
        Purpose.CAREER: (
            "Audience: a peer or senior whose work overlaps yours, "
            "approached for networking or mentorship."
        ),
        Purpose.BRAND: (
            "Audience: your professional network. Build credibility around "
            "the topic below; do not pitch a product."
        ),
        Purpose.SERVICE: (
            "Audience: prospective clients who might pay for the service/"
            "product described below. Value-first; one CTA."
        ),
    }
    return f"{purpose_blurbs[purpose]}\n\nContext from the author:\n{user_context}"


def generate_drafts(
    senso: Senso,
    purpose: Purpose | str,
    context: str,
    session_id: str,
    logger: Any | None = None,
) -> list[DraftCard]:
    """Generate one draft card per channel mapped to `purpose`.

    `logger` is an `outreach.log` module reference or any object exposing
    `log_generate(...)`. Passing it explicitly keeps the function testable.
    """
    if isinstance(purpose, str):
        purpose = Purpose(purpose)

    full_context = _build_context(purpose, context)
    cards: list[DraftCard] = []

    for channel in channels_for(purpose):
        ct_config = CONTENT_TYPE_CONFIGS.get(channel, {"template": ""})
        with trace.step(
            session_id,
            "senso.generate",
            purpose=purpose.value,
            channel=channel,
        ) as ctx:
            try:
                ct_id = senso.get_or_create_content_type(channel, ct_config)
                ctx["content_type_id"] = ct_id
                job_id = senso.generate_sample(ct_id, full_context)
                ctx["job_id"] = job_id
                job = senso.poll_until_done(job_id, timeout_s=30.0, interval_s=1.0)
                md = job.get("result", {}).get("raw_markdown", "")
                draft_id = job.get("result", {}).get("content_id", "")
                ctx["draft_chars"] = len(md)
                if logger is not None:
                    logger.log_generate(
                        user_id="demo",
                        purpose=purpose.value,
                        channel=channel,
                        content_type_id=ct_id,
                        sample_job_id=job_id,
                    )
                cards.append(DraftCard(
                    channel=channel,
                    content_type_id=ct_id,
                    sample_job_id=job_id,
                    markdown=md,
                    draft_id=draft_id,
                ))
            except Exception as exc:  # noqa: BLE001 -- demo path
                ctx["error"] = str(exc)
                cards.append(DraftCard(
                    channel=channel,
                    content_type_id="",
                    sample_job_id="",
                    markdown="",
                    error=str(exc),
                ))
    return cards
