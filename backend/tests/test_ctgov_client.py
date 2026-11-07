"""ClinicalTrials.gov client: parsing, pagination, invalid ids, network failures, rate limits."""

import httpx
import pytest
import respx

from app.services.clinicaltrials_client import (
    ClinicalTrialsClient, CTGovError, CTGovUnavailable, InvalidNCTId, StudyNotFound, validate_nct_id,
)
from tests.conftest import load_fixture

BASE = "https://clinicaltrials.gov/api/v2"


def client(**kw):
    return ClinicalTrialsClient(base_url=BASE, requests_per_minute=100000, backoff_base=0.0, **kw)


def test_validate_nct_id():
    assert validate_nct_id(" nct01234567 ") == "NCT01234567"
    for bad in ["NCT123", "12345678", "NCT0123456789", "NCT0123456X", ""]:
        with pytest.raises(InvalidNCTId):
            validate_nct_id(bad)


@pytest.mark.asyncio
@respx.mock
async def test_search_parses_real_recorded_response():
    fx = load_fixture("search_breast_her2.json")
    route = respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json=fx))
    res = await client().search(condition="HER2-positive breast cancer", statuses=["RECRUITING"], max_results=5)
    assert res.total_count == fx["totalCount"]
    assert [s["protocolSection"]["identificationModule"]["nctId"] for s in res.studies][0] == "NCT04646759"
    params = route.calls[0].request.url.params
    assert params["query.cond"] == "HER2-positive breast cancer"
    assert params["filter.overallStatus"] == "RECRUITING"
    assert params["countTotal"] == "true"


@pytest.mark.asyncio
@respx.mock
async def test_pagination_follows_next_page_token():
    fx = load_fixture("search_nsclc_egfr.json")["studies"]
    page1 = {"studies": fx[:3], "nextPageToken": "TOKEN2", "totalCount": 5}
    page2 = {"studies": fx[3:5]}
    route = respx.get(f"{BASE}/studies").mock(side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)])
    res = await client().search(condition="lung cancer", max_results=10, page_size=3)
    assert len(res.studies) == 5 and res.pages_fetched == 2 and res.total_count == 5
    assert route.calls[1].request.url.params["pageToken"] == "TOKEN2"
    assert "countTotal" not in route.calls[1].request.url.params  # only requested on the first page


@pytest.mark.asyncio
@respx.mock
async def test_pagination_stops_at_max_results():
    fx = load_fixture("search_nsclc_egfr.json")["studies"]
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json={"studies": fx[:2], "nextPageToken": "X"}))
    res = await client().search(condition="lung cancer", max_results=4, page_size=2)
    assert len(res.studies) == 4 and res.pages_fetched == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_study_not_found_and_invalid():
    respx.get(f"{BASE}/studies/NCT99999999").mock(return_value=httpx.Response(404, text="NCT number NCT99999999 not found"))
    with pytest.raises(StudyNotFound):
        await client().get_study("NCT99999999")
    with pytest.raises(InvalidNCTId):
        await client().get_study("BADID")


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_429_is_retried_then_succeeds():
    fx = load_fixture("search_cf.json")
    route = respx.get(f"{BASE}/studies").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(503), httpx.Response(200, json=fx)])
    res = await client().search(condition="cystic fibrosis", max_results=5)
    assert route.call_count == 3 and len(res.studies) == 5


@pytest.mark.asyncio
@respx.mock
async def test_persistent_failure_raises_explicit_unavailable():
    respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(503))
    with pytest.raises(CTGovUnavailable, match="could not be retrieved"):
        await client(max_retries=2).search(condition="x")


@pytest.mark.asyncio
@respx.mock
async def test_network_error_raises_unavailable():
    respx.get(f"{BASE}/studies").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(CTGovUnavailable):
        await client(max_retries=1).search(condition="x")


@pytest.mark.asyncio
async def test_rejects_unknown_status_filter_and_empty_query():
    c = client()
    with pytest.raises(CTGovError):
        await c.search_page(condition="x", statuses=["OPEN"])
    with pytest.raises(CTGovError):
        await c.search_page()


@pytest.mark.asyncio
@respx.mock
async def test_geo_filter_format():
    route = respx.get(f"{BASE}/studies").mock(return_value=httpx.Response(200, json={"studies": []}))
    await client().search_page(condition="x", geo=(42.36011, -71.05894, 100))
    assert route.calls[0].request.url.params["filter.geo"] == "distance(42.3601,-71.0589,100mi)"
