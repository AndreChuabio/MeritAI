import pytest

from paperpilot.outreach.purpose import Purpose, PURPOSE_CHANNELS, channels_for


def test_purpose_enum_has_five_values():
    assert {p.value for p in Purpose} == {"VISA", "CAREER", "NETWORK", "BRAND", "SERVICE"}


def test_network_targets_collab_email_and_linkedin_dm():
    assert channels_for(Purpose.NETWORK) == ["email_collaboration", "linkedin_dm_career"]


def test_purpose_channels_covers_all_purposes():
    assert set(PURPOSE_CHANNELS.keys()) == set(Purpose)


def test_visa_targets_speaker_and_collaboration_emails():
    assert channels_for(Purpose.VISA) == ["email_speaker_pitch", "email_collaboration"]


def test_career_targets_linkedin_dm():
    assert channels_for(Purpose.CAREER) == ["linkedin_dm_career"]


def test_brand_targets_linkedin_post_and_x_thread():
    assert channels_for(Purpose.BRAND) == ["linkedin_post_brand", "x_thread_brand"]


def test_service_targets_three_channels():
    assert channels_for(Purpose.SERVICE) == [
        "linkedin_post_brand",
        "email_service",
        "x_thread_brand",
    ]


def test_channels_for_accepts_string_purpose():
    assert channels_for("VISA") == channels_for(Purpose.VISA)


def test_channels_for_rejects_unknown_purpose():
    with pytest.raises(ValueError):
        channels_for("MYSTERY")
