import pytest
import responses

from paperpilot.outreach.senso import Senso, SensoAPIError


# ---- Task 3: auth, base URL, error type ----

@responses.activate
def test_senso_sends_api_key_header():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/brand-kit",
        json={"brand_name": "Nikki"},
        status=200,
    )
    s = Senso(api_key="test-key")
    s.get_brand_kit()
    assert responses.calls[0].request.headers["X-API-Key"] == "test-key"


@responses.activate
def test_senso_raises_on_non_2xx():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/brand-kit",
        json={"error": "nope"},
        status=403,
    )
    s = Senso(api_key="test-key")
    with pytest.raises(SensoAPIError) as exc_info:
        s.get_brand_kit()
    assert exc_info.value.status == 403


@responses.activate
def test_senso_respects_custom_base_url():
    responses.add(
        responses.GET,
        "https://staging.senso.ai/v1/org/brand-kit",
        json={"brand_name": "Nikki"},
        status=200,
    )
    s = Senso(api_key="k", base="https://staging.senso.ai/v1")
    s.get_brand_kit()
    assert responses.calls[0].request.url.startswith("https://staging.senso.ai/v1/")


# ---- Task 4: PUT brand kit ----

@responses.activate
def test_put_brand_kit_sends_payload():
    captured = {}

    def cb(request):
        captured["body"] = request.body
        return (200, {}, '{"ok": true}')

    responses.add_callback(
        responses.PUT,
        "https://apiv2.senso.ai/api/v1/org/brand-kit",
        callback=cb,
        content_type="application/json",
    )

    s = Senso(api_key="k")
    s.put_brand_kit({
        "brand_name": "Nikki Hu",
        "brand_description": "Clinical ML engineer",
        "voice_and_tone": "warm, evidence-based",
        "guidelines": {"links": {"scholar": "https://scholar.google.com/..."}},
    })
    assert b'"brand_name": "Nikki Hu"' in captured["body"]
    assert b'"voice_and_tone"' in captured["body"]


# ---- Task 5: content types ----

@responses.activate
def test_list_content_types_returns_items():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"items": [{"id": "a", "name": "linkedin_post_brand"}]},
        status=200,
    )
    s = Senso(api_key="k")
    items = s.list_content_types()
    assert items == [{"id": "a", "name": "linkedin_post_brand"}]


@responses.activate
def test_create_content_type_posts_name_and_config():
    captured = {}

    def cb(request):
        captured["body"] = request.body
        return (201, {}, '{"id": "ct-new"}')

    responses.add_callback(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        callback=cb,
        content_type="application/json",
    )
    s = Senso(api_key="k")
    result = s.create_content_type("x_thread_brand", {"template": "4-6 tweets"})
    assert result == {"id": "ct-new"}
    assert b'"name": "x_thread_brand"' in captured["body"]
    assert b'"template": "4-6 tweets"' in captured["body"]


@responses.activate
def test_get_or_create_returns_existing_id_without_post():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"items": [{"id": "ct-existing", "name": "linkedin_dm_career"}]},
        status=200,
    )
    s = Senso(api_key="k")
    ctid = s.get_or_create_content_type("linkedin_dm_career", {"template": "ignored"})
    assert ctid == "ct-existing"
    assert len(responses.calls) == 1


@responses.activate
def test_get_or_create_creates_when_missing():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"items": []},
        status=200,
    )
    responses.add(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/content-types",
        json={"id": "ct-fresh"},
        status=201,
    )
    s = Senso(api_key="k")
    ctid = s.get_or_create_content_type("new_thing", {"template": "..."})
    assert ctid == "ct-fresh"
    assert len(responses.calls) == 2


# ---- Task 6: content generation ----

@responses.activate
def test_generate_sample_returns_job_id():
    responses.add(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample",
        json={"sample_job_id": "job-abc", "status": "queued"},
        status=200,
    )
    s = Senso(api_key="k")
    job_id = s.generate_sample(content_type_id="ct-1", context="hello")
    assert job_id == "job-abc"
    body = responses.calls[0].request.body
    assert b'"content_type_id": "ct-1"' in body
    assert b'"context": "hello"' in body


@responses.activate
def test_poll_until_done_returns_completed_result():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample-jobs/job-abc",
        json={"status": "running"},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample-jobs/job-abc",
        json={"status": "completed", "result": {"raw_markdown": "hi"}},
        status=200,
    )
    s = Senso(api_key="k")
    out = s.poll_until_done("job-abc", interval_s=0.01, timeout_s=2.0)
    assert out["result"]["raw_markdown"] == "hi"


@responses.activate
def test_poll_until_done_raises_on_timeout():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/content-generation/sample-jobs/stuck",
        json={"status": "running"},
        status=200,
    )
    s = Senso(api_key="k")
    with pytest.raises(TimeoutError):
        s.poll_until_done("stuck", interval_s=0.01, timeout_s=0.05)


# ---- Task 7: KB, product lines, citation trends, drafts ----

@responses.activate
def test_kb_ingest_posts_title_and_body():
    responses.add(
        responses.POST,
        "https://apiv2.senso.ai/api/v1/org/knowledge-base/ingest",
        json={"id": "kb-1"},
        status=200,
    )
    s = Senso(api_key="k")
    out = s.kb_ingest(title="Paper Summary", body="...", source_url="https://x")
    assert out["id"] == "kb-1"


@responses.activate
def test_list_product_lines():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/product-lines",
        json={"items": [{"id": "pl-1", "name": "PaperPilot"}]},
        status=200,
    )
    s = Senso(api_key="k")
    assert s.list_product_lines() == [{"id": "pl-1", "name": "PaperPilot"}]


@responses.activate
def test_citation_trends_owned():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/citation-trends/owned",
        json={"total": 12, "by_day": [{"d": "2026-05-22", "n": 3}]},
        status=200,
    )
    s = Senso(api_key="k")
    out = s.citation_trends("owned")
    assert out["total"] == 12


@responses.activate
def test_list_drafts_returns_items():
    responses.add(
        responses.GET,
        "https://apiv2.senso.ai/api/v1/org/drafts",
        json={"items": [{"id": "d1"}]},
        status=200,
    )
    s = Senso(api_key="k")
    items = s.list_drafts(limit=5)
    assert items == [{"id": "d1"}]
    # Verify limit was sent as a query parameter.
    assert "limit=5" in responses.calls[0].request.url
