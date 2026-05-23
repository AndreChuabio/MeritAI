from unittest.mock import MagicMock, patch

from paperpilot.outreach.github_repos import (
    extract_username,
    list_user_repos,
)


def test_extract_username_handles_trailing_slash():
    assert extract_username("https://github.com/huhu42/") == "huhu42"
    assert extract_username("https://github.com/huhu42") == "huhu42"
    assert extract_username("http://github.com/huhu42") == "huhu42"
    assert extract_username("github.com/huhu42") == "huhu42"


def test_extract_username_returns_none_for_invalid():
    assert extract_username("") is None
    assert extract_username("not a url") == "not a url"  # best-effort, last segment


def test_list_user_repos_returns_serialized_dicts():
    fake_repo = MagicMock()
    fake_repo.name = "agentichack"
    fake_repo.html_url = "https://github.com/huhu42/agentichack"
    fake_repo.description = "Hackathon project"
    fake_repo.stargazers_count = 3
    fake_repo.language = "Python"

    fake_user = MagicMock()
    fake_user.get_repos.return_value = [fake_repo]

    fake_github = MagicMock()
    fake_github.get_user.return_value = fake_user

    with patch("paperpilot.outreach.github_repos.Github", return_value=fake_github):
        out = list_user_repos("https://github.com/huhu42", token="t")

    assert out == [{
        "name": "agentichack",
        "url": "https://github.com/huhu42/agentichack",
        "description": "Hackathon project",
        "stars": 3,
        "language": "Python",
    }]


def test_list_user_repos_empty_on_invalid_url():
    assert list_user_repos("", token="t") == []
