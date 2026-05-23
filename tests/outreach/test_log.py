from unittest.mock import MagicMock

from paperpilot.outreach.log import (
    log_generate,
    mark_posted,
    upsert_user_profile,
    count_posted,
    UserProfile,
)


def test_upsert_user_profile_inserts_row():
    client = MagicMock()
    profile = UserProfile(
        user_id="demo",
        name="Nikki",
        title="ML Eng",
        about="Clinical ML",
        voice_tone="warm",
        github_url="https://github.com/x",
        linkedin_url="https://linkedin.com/in/x",
        scholar_url="https://scholar.google.com/x",
        site_url="https://x.dev",
        resume_text="...",
    )
    upsert_user_profile(profile, client=client)
    client.insert.assert_called_once()
    args, kwargs = client.insert.call_args
    assert args[0] == "user_profile"
    row = args[1][0]
    assert row[0] == "demo"
    assert row[1] == "Nikki"


def test_log_generate_writes_row_and_returns_id():
    client = MagicMock()
    row_id = log_generate(
        user_id="demo",
        purpose="VISA",
        channel="email_speaker_pitch",
        content_type_id="ct-1",
        sample_job_id="job-1",
        client=client,
    )
    assert isinstance(row_id, str) and row_id
    client.insert.assert_called_once()


def test_mark_posted_updates_row():
    client = MagicMock()
    mark_posted(sample_job_id="job-1", draft_id="d-1", client=client)
    client.command.assert_called_once()
    cmd = client.command.call_args[0][0]
    assert "ALTER TABLE outreach_log" in cmd
    assert "posted = 1" in cmd


def test_count_posted_returns_int():
    client = MagicMock()
    client.query.return_value.result_rows = [[7]]
    assert count_posted("demo", client=client) == 7
