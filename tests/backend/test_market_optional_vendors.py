"""Missing vendor keys degrade the surface, they do not break it."""

from backend.services import market_service


def test_people_search_without_nimble_is_not_an_error(monkeypatch):
    """No Nimble key yields an explained empty result, not an exception."""
    monkeypatch.delenv("NIMBLE_API_KEY", raising=False)
    result = market_service.suggest_people(
        user_id="11111111-1111-1111-1111-111111111111",
        purpose="NETWORK",
        context="pgvector researchers",
    )
    assert result["configured"] is False
    assert result["people"] == []
    assert "enter the recipient" in result["reason"].lower()
