import pytest
import responses

from paperpilot.outreach.scholar import (
    fetch_mock,
    fetch_via_nimble,
    ScholarData,
    O1_THRESHOLD,
)


def test_fetch_mock_loads_seed_file():
    data = fetch_mock()
    assert isinstance(data, ScholarData)
    assert data.total_citations == 14
    assert len(data.by_month) == 10


def test_o1_threshold_constant_is_20():
    assert O1_THRESHOLD == 20


def test_progress_to_o1_fraction():
    data = fetch_mock()
    assert 0.0 <= data.progress_to_o1() <= 1.0
    assert abs(data.progress_to_o1() - 0.7) < 1e-6


@responses.activate
def test_fetch_via_nimble_parses_total_citations():
    # Nimble returns the rendered Scholar HTML in `.html_content`.
    html = """
    <html><body>
      <table id="gsc_rsb_st">
        <tr><td class="gsc_rsb_std">42</td><td class="gsc_rsb_std">28</td></tr>
        <tr><td class="gsc_rsb_std">8</td><td class="gsc_rsb_std">6</td></tr>
      </table>
      <div id="gsc_a_b">
        <tr class="gsc_a_tr">
          <td class="gsc_a_t"><a class="gsc_a_at">Federated LLMs for Clinical Notes</a></td>
          <td class="gsc_a_c"><a class="gsc_a_ac">7</a></td>
          <td class="gsc_a_y"><span class="gsc_a_h">2025</span></td>
        </tr>
      </div>
    </body></html>
    """
    responses.add(
        responses.POST,
        "https://api.webit.live/api/v1/realtime/web",
        json={"html_content": html, "status": {"code": 200}},
        status=200,
    )
    data = fetch_via_nimble(
        scholar_url="https://scholar.google.com/citations?user=ABC",
        api_key="nimble-test-key",
    )
    assert data.total_citations == 42
    assert data.h_index == 8
    # The papers array picks up at least one entry from the table.
    assert any(p["title"] == "Federated LLMs for Clinical Notes" for p in data.papers)


@responses.activate
def test_fetch_via_nimble_raises_on_error_status():
    responses.add(
        responses.POST,
        "https://api.webit.live/api/v1/realtime/web",
        json={"status": {"code": 500, "message": "scrape failed"}},
        status=200,
    )
    with pytest.raises(RuntimeError):
        fetch_via_nimble(
            scholar_url="https://scholar.google.com/citations?user=ABC",
            api_key="nimble-test-key",
        )
