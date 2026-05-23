from unittest.mock import MagicMock

from paperpilot.outreach.log import (
    log_generate,
    mark_posted,
    upsert_user_profile,
    find_user_profile_by_name,
    count_posted,
    count_by_channel,
    count_by_purpose,
    drafts_by_day,
    total_drafts,
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


def test_count_by_channel_returns_mapping():
    client = MagicMock()
    client.query.return_value.result_rows = [
        ("linkedin_post_brand", 4),
        ("x_thread_brand", 2),
        ("email_speaker_pitch", 3),
    ]
    out = count_by_channel("demo", client=client)
    assert out == {
        "linkedin_post_brand": 4,
        "x_thread_brand": 2,
        "email_speaker_pitch": 3,
    }


def test_count_by_purpose_returns_mapping():
    client = MagicMock()
    client.query.return_value.result_rows = [
        ("VISA", 5),
        ("BRAND", 3),
    ]
    out = count_by_purpose("demo", client=client)
    assert out == {"VISA": 5, "BRAND": 3}


def test_drafts_by_day_returns_list_of_pairs():
    client = MagicMock()
    client.query.return_value.result_rows = [
        ("2026-05-21", 2),
        ("2026-05-22", 5),
        ("2026-05-23", 3),
    ]
    out = drafts_by_day("demo", client=client)
    assert out == [
        {"date": "2026-05-21", "count": 2},
        {"date": "2026-05-22", "count": 5},
        {"date": "2026-05-23", "count": 3},
    ]


def test_total_drafts_returns_int():
    client = MagicMock()
    client.query.return_value.result_rows = [[12]]
    assert total_drafts("demo", client=client) == 12


def test_find_user_profile_by_name_hit():
    client = MagicMock()
    client.query.return_value.result_rows = [(
        "nikki_hu", "Nikki Hu", "Software Engineer", "Bio",
        "professional", "https://github.com/huhu42",
        "https://linkedin.com/in/nikkihu", "", "", "",
    )]
    p = find_user_profile_by_name("nikki hu", client=client)
    assert p is not None
    assert p.user_id == "nikki_hu"
    assert p.name == "Nikki Hu"
    assert p.github_url == "https://github.com/huhu42"


def test_find_user_profile_by_name_miss():
    client = MagicMock()
    client.query.return_value.result_rows = []
    assert find_user_profile_by_name("ghost", client=client) is None
