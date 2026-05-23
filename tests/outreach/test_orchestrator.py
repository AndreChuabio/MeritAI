from unittest.mock import MagicMock

from paperpilot.outreach.orchestrator import generate_drafts, DraftCard
from paperpilot.outreach.purpose import Purpose


def test_generate_drafts_returns_one_card_per_channel():
    senso = MagicMock()
    senso.get_or_create_content_type.side_effect = lambda name, cfg: f"ct-{name}"
    senso.generate_sample.side_effect = lambda content_type_id, context: f"job-{content_type_id}"
    senso.poll_until_done.side_effect = lambda jid, **kw: {
        "status": "completed",
        "result": {
            "raw_markdown": f"draft for {jid}",
            "content_id": f"d-{jid}",
        },
    }

    cards = generate_drafts(
        senso=senso,
        purpose=Purpose.BRAND,
        context="ML4H paper on retrieval calibration",
        session_id="sess_test",
        logger=MagicMock(),
    )

    assert [c.channel for c in cards] == ["linkedin_post_brand", "x_thread_brand"]
    assert all(isinstance(c, DraftCard) for c in cards)
    assert all(c.markdown.startswith("draft for job-ct-") for c in cards)
    assert all(c.sample_job_id.startswith("job-ct-") for c in cards)


def test_generate_drafts_continues_when_one_channel_fails():
    senso = MagicMock()
    senso.get_or_create_content_type.side_effect = lambda name, cfg: f"ct-{name}"

    def gen(content_type_id, context):
        if "x_thread" in content_type_id:
            raise RuntimeError("simulated failure")
        return f"job-{content_type_id}"

    senso.generate_sample.side_effect = gen
    senso.poll_until_done.side_effect = lambda jid, **kw: {
        "status": "completed",
        "result": {"raw_markdown": f"draft for {jid}", "content_id": "d"},
    }

    cards = generate_drafts(
        senso=senso,
        purpose=Purpose.BRAND,
        context="ctx",
        session_id="sess_test",
        logger=MagicMock(),
    )

    assert len(cards) == 2
    assert cards[0].error is None
    assert cards[1].error is not None
    assert cards[1].markdown == ""


def test_generate_drafts_calls_logger_for_each_success():
    senso = MagicMock()
    senso.get_or_create_content_type.side_effect = lambda name, cfg: f"ct-{name}"
    senso.generate_sample.side_effect = lambda content_type_id, context: f"job-{content_type_id}"
    senso.poll_until_done.side_effect = lambda jid, **kw: {
        "status": "completed",
        "result": {"raw_markdown": "x", "content_id": "d"},
    }
    logger = MagicMock()

    generate_drafts(
        senso=senso,
        purpose=Purpose.SERVICE,
        context="ctx",
        session_id="sess_test",
        logger=logger,
    )
    # SERVICE has 3 channels -> 3 log_generate calls.
    assert logger.log_generate.call_count == 3
