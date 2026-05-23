import pytest
import responses

from paperpilot.outreach.nimble import NimbleClient, NimbleAPIError


@responses.activate
def test_search_returns_results_list():
    responses.add(
        responses.POST,
        "https://sdk.nimbleway.com/v1/search",
        json={
            "results": [
                {
                    "title": "Jane Doe - ML researcher",
                    "description": "ML researcher at Foo",
                    "url": "https://linkedin.com/in/janedoe",
                },
            ],
            "total_results": 1,
            "request_id": "req-1",
        },
        status=200,
    )
    n = NimbleClient(api_key="nimble-test")
    results = n.search("clinical ML researchers in NYC", focus="social", max_results=5)
    assert len(results) == 1
    assert results[0]["url"] == "https://linkedin.com/in/janedoe"
    # Verify auth header
    assert responses.calls[0].request.headers["Authorization"] == "Bearer nimble-test"
    body = responses.calls[0].request.body
    assert b'"query": "clinical ML researchers in NYC"' in body
    assert b'"focus": "social"' in body
    assert b'"max_results": 5' in body


@responses.activate
def test_search_raises_on_non_2xx():
    responses.add(
        responses.POST,
        "https://sdk.nimbleway.com/v1/search",
        json={"error": "rate_limited"},
        status=429,
    )
    n = NimbleClient(api_key="k")
    with pytest.raises(NimbleAPIError) as exc_info:
        n.search("x")
    assert exc_info.value.status == 429


@responses.activate
def test_find_people_targets_linkedin_with_focus_social():
    responses.add(
        responses.POST,
        "https://sdk.nimbleway.com/v1/search",
        json={"results": [{"title": "X", "description": "y", "url": "https://linkedin.com/in/x"}]},
        status=200,
    )
    n = NimbleClient(api_key="k")
    out = n.find_people(criteria="ML researchers clinical NYC", limit=3)
    body = responses.calls[0].request.body
    assert b"linkedin.com" in body  # query is augmented with site:linkedin.com/in
    assert b'"focus": "social"' in body
    assert b'"max_results": 3' in body
    assert out == [{"title": "X", "description": "y", "url": "https://linkedin.com/in/x"}]
