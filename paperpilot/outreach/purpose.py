"""Purpose enum + purpose -> channel mapping for outreach drafts."""

from __future__ import annotations

from enum import Enum


class Purpose(str, Enum):
    VISA = "VISA"
    CAREER = "CAREER"
    NETWORK = "NETWORK"
    BRAND = "BRAND"
    SERVICE = "SERVICE"


PURPOSE_CHANNELS: dict[Purpose, list[str]] = {
    Purpose.VISA:    ["email_speaker_pitch", "email_collaboration"],
    Purpose.CAREER:  ["linkedin_dm_career"],
    Purpose.NETWORK: ["email_collaboration", "linkedin_dm_career"],
    Purpose.BRAND:   ["linkedin_post_brand", "x_thread_brand"],
    Purpose.SERVICE: ["linkedin_post_brand", "email_service", "x_thread_brand"],
}


def channels_for(purpose: Purpose | str) -> list[str]:
    """Return the ordered list of channel content-type names for a purpose."""
    if isinstance(purpose, str):
        try:
            purpose = Purpose(purpose)
        except ValueError as exc:
            raise ValueError(f"Unknown purpose: {purpose!r}") from exc
    return list(PURPOSE_CHANNELS[purpose])
