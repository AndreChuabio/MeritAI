"""Outreach drafting works with an LLM key alone, no Senso account."""

import pytest

from paperpilot.outreach import llm_draft
from paperpilot.outreach.orchestrator import generate_drafts
from paperpilot.outreach.purpose import Purpose


class _FakeCompletions:
    def __init__(self, text):
        self._text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Msg:
            content = self._text

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _FakeClient:
    def __init__(self, text="drafted markdown"):
        self.chat = type("chat", (), {"completions": _FakeCompletions(text)})()


def test_draft_channel_builds_prompt_from_content_type(monkeypatch):
    """The channel's template and writing rules are what shape the prompt."""
    fake = _FakeClient()
    monkeypatch.setattr(llm_draft, "get_client", lambda: fake)

    out = llm_draft.draft_channel("linkedin_dm", "Audience: a peer.\n\nContext: x")

    assert out == "drafted markdown"
    prompt = fake.chat.completions.calls[0]["messages"][1]["content"]
    assert "under 600 chars" in prompt
    assert "End with one explicit ask." in prompt
    assert "Audience: a peer." in prompt


def test_generate_drafts_needs_no_senso(monkeypatch):
    """With senso=None, every channel still produces a card with markdown."""
    fake = _FakeClient("hello there")
    monkeypatch.setattr(llm_draft, "get_client", lambda: fake)

    cards = generate_drafts(
        senso=None,
        purpose=Purpose.NETWORK,
        context="I work on pgvector retrieval.",
        session_id="sess_test",
        user_id="11111111-1111-1111-1111-111111111111",
        logger=None,
    )

    # NETWORK maps to two channels in purpose.PURPOSE_CHANNELS.
    assert len(cards) == 2
    assert all(c.markdown == "hello there" for c in cards)
    assert all(c.error is None for c in cards)


def test_one_channel_failing_does_not_cancel_the_others(monkeypatch):
    """A failure is isolated to its own card, as before."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model unavailable")
        return _FakeClient("second one worked")

    monkeypatch.setattr(llm_draft, "get_client", flaky)

    cards = generate_drafts(
        senso=None,
        purpose=Purpose.NETWORK,
        context="ctx",
        session_id="sess_test",
        user_id="11111111-1111-1111-1111-111111111111",
        logger=None,
    )
    assert cards[0].error is not None
    assert cards[1].markdown == "second one worked"
