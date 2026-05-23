"""Templates used by Senso to shape generated content.

These map 1:1 to the channels referenced in `purpose.PURPOSE_CHANNELS`.
The seed script creates one Senso content type per entry here; the
orchestrator passes the matching config into `get_or_create_content_type`
so the type is created on first run if a fresh workspace is connected.
"""

from __future__ import annotations


CONTENT_TYPE_CONFIGS: dict[str, dict] = {
    "linkedin_post_brand": {
        "template": (
            "A first-person LinkedIn post, 200-300 words. Open with a hook, "
            "deliver one concrete insight, end with a single question to the "
            "reader. No emojis. No hashtags."
        ),
        "writing_rules": "Under 1300 chars. Plain text. No links inline.",
    },
    "linkedin_dm_career": {
        "template": (
            "A short LinkedIn direct message, under 600 chars. Warm intro "
            "tone, reference one shared interest, end with one explicit ask."
        ),
        "writing_rules": "Address by first name if known. No corporate jargon.",
    },
    "x_thread_brand": {
        "template": (
            "A 4-6 tweet thread. First tweet hooks; each subsequent tweet "
            "delivers one point; last tweet has a CTA. Number each tweet `1/`."
        ),
        "writing_rules": "Each tweet <= 280 characters.",
    },
    "email_speaker_pitch": {
        "template": (
            "A formal pitch email to a conference organizer. Subject line on "
            "the first line. Body 150-250 words. Names a specific session "
            "slot and concrete topic the author can speak on."
        ),
        "writing_rules": "Sign with the author's name. No emojis.",
    },
    "email_collaboration": {
        "template": (
            "A warm academic outreach email asking about collaboration. "
            "Reference a shared topic explicitly. 150-250 words. Soft ask."
        ),
        "writing_rules": "Reply-friendly closing.",
    },
    "email_service": {
        "template": (
            "A value-first service outreach email. Open with what the "
            "recipient gets. 150-200 words. One CTA only, in the last line."
        ),
        "writing_rules": "No hard sell language.",
    },
}
