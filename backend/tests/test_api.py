"""API integration: full match pipeline (real recorded records -> DB -> pgvector -> rules -> fake Claude -> session),
explicit outage errors, sessions, explanations, comparison, follow-ups and privacy behavior."""

import json
import logging
import re

import httpx
import pytest

from app.data.demo_profiles import DEMOS
from app.main import app
from app.services import llm as llm_mod
from app.services.clinicaltrials_client import ClinicalTrialsClient
from tests.conftest import FakeLLM, load_fixture

BASE = "https://clinicaltrials.gov/api/v2"


def ctgov_handler(state: dict):
    breast = load_fixture("search_breast_her2.json")
    by_id = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in breast["studies"]}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] = state.get("calls", 0) + 1
        if state.get("down"):
            return httpx.Response(503)
        path = request.url.path
        if path.endswith("/version"):
            return httpx.Response(200, json={"apiVersion": "2.0.5", "dataTimestamp": "2026-11-06T10:00:05"})
        if path.endswith("/studies"):
            return httpx.Response(200, json=breast)
        m = re.search(r"/studies/(NCT\d{8})$", path)
        if m:
            return httpx.Response(200, json=by_id[m.group(1)]) if m.group(1) in by_id else httpx.Response(404)
        return httpx.Response(400)
    return handler


def generic_assessment(user: str) -> dict:
    """A well-formed, conservative fake Claude answer derived from the prompt itself."""
    nct = re.search(r'nct_id="(NCT\d{8})"', user).group(1)
    ids = re.findall(r'<criterion id="(\w+)"', user)
    return {"nct_id": nct, "profile_conflicts": [],
            "criteria": [{"criterion_id": i, "assessment": "UNKNOWN", "trial_evidence": "", "patient_evidence": [],
                          "explanation": "Not stated in the profile.", "unknown_reason": "requires_screening_test",
                          "impact": "routine"} for i in ids],
            "summary": f"Screening tests are needed to check [{ids[0]}]." if ids else "No criteria."}


@pytest.fixture
async def api(db):
    state: dict = {}
    app.state.ctgov = ClinicalTrialsClient(httpx.AsyncClient(transport=httpx.MockTransport(ctgov_handler(state))),
                                           base_url=BASE, requests_per_minute=100000, backoff_base=0.0, max_retries=1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.state = state
        yield c


def breast_profile():
    return json.loads(DEMOS[0]["profile"].model_dump_json())


async def test_health_exposes_no_secrets(api, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")
    r = await api.get("/api/health")
    assert r.status_code == 200 and r.json()["database"] == "ok" and r.json()["pgvector"] == "ok"
    assert "sk-ant" not in r.text


async def test_match_end_to_end_with_embeddings_and_fake_claude(api, fake_embedder):
    llm_mod.set_llm(FakeLLM({"LLMTrialAssessment": generic_assessment}))
    r = await api.post("/api/trials/match", json={"profile": breast_profile(), "max_results": 5})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["data"]["source"] == "live" and d["data"]["api_data_timestamp"] == "2026-11-06T10:00:05"
    assert d["stats"]["candidates_retrieved"] == 5 and d["stats"]["ai_analyzed"] >= 1
    fixture_ids = {s["protocolSection"]["identificationModule"]["nctId"] for s in load_fixture("search_breast_her2.json")["studies"]}
    for res in d["results"]:
        assert res["trial"]["nct_id"] in fixture_ids  # nothing invented
        assert res["trial"]["url"] == f"https://clinicaltrials.gov/study/{res['trial']['nct_id']}"
        assert any(c["name"] == "semantic" and c["score"] is not None for c in res["relevance"]["components"])
        assert "not a probability of eligibility" in res["relevance"]["note"]
        assert res["eligibility"]["category"] in {"POTENTIAL_MATCH", "NEEDS_MORE_INFORMATION",
                                                   "POTENTIALLY_INELIGIBLE", "REQUIRES_CLINICAL_REVIEW"}
        assert "%" not in res["eligibility"]["headline"]
    # Blocked studies always rank after unblocked ones.
    cats = [r["eligibility"]["category"] == "POTENTIALLY_INELIGIBLE" for r in d["results"]]
    assert cats == sorted(cats)
    assert "final eligibility" in d["disclaimer"].lower()

    # Session retrieval + explicit deletion.
    sid, nct = d["session_id"], d["results"][0]["trial"]["nct_id"]
    assert (await api.get(f"/api/sessions/{sid}/results/{nct}")).status_code == 200
    assert (await api.delete(f"/api/sessions/{sid}")).status_code == 204
    assert (await api.get(f"/api/sessions/{sid}/results/{nct}")).status_code == 404


async def test_second_match_is_served_from_cache(api):
    await api.post("/api/trials/match", json={"profile": breast_profile(), "max_results": 3})
    calls = api.state["calls"]
    r = await api.post("/api/trials/match", json={"profile": breast_profile(), "max_results": 3})
    assert r.json()["data"]["source"] == "cache"
    assert api.state["calls"] == calls + 1  # only the /version check


async def test_without_claude_no_ai_assessments_are_fabricated(api):
    r = await api.post("/api/trials/match", json={"profile": breast_profile(), "max_results": 5})
    d = r.json()
    assert d["ai_enabled"] is False and any("not configured" in w for w in d["warnings"])
    for res in d["results"]:
        assert res["ai_status"] != "ok"
        assert all(c["source"] in ("rule", "not_assessed") for c in res["criteria"])
        assert res["eligibility"]["category"] != "POTENTIAL_MATCH"


async def test_ctgov_outage_returns_explicit_error_not_fake_data(api):
    api.state["down"] = True
    r = await api.post("/api/trials/match", json={"profile": breast_profile()})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "live_data_unavailable"


async def test_trial_detail_invalid_and_missing(api):
    assert (await api.get("/api/trials/NOT-AN-ID")).status_code == 422
    assert (await api.get("/api/trials/NCT99999999")).status_code == 404
    r = await api.get("/api/trials/NCT04646759")
    assert r.status_code == 200 and r.json()["data_source"] == "live"
    assert (await api.get("/api/trials/NCT04646759")).json()["data_source"] == "cache"


async def test_match_requires_condition(api):
    assert (await api.post("/api/trials/match", json={"profile": {}})).status_code == 422


async def test_explain_rules_fallback_and_claude_validation(api):
    r = await api.post("/api/trials/NCT04646759/explain", json={"mode": "patient"})
    d = r.json()
    assert d["source"] == "rules" and [s["heading"] for s in d["sections"]] == [
        "What is this study testing?", "Why might this trial fit?", "What still needs to be checked?"]

    llm_mod.set_llm(FakeLLM({"LLMExplanation": {
        "nct_id": "NCT04646759", "what_is_tested": "A treatment.", "why_might_fit": "Matches [I1] and [I99].",
        "what_to_check": "Confirm [E1].", "questions_for_team": ["What visits are needed?"]}}))
    d = (await api.post("/api/trials/NCT04646759/explain", json={"mode": "clinical"})).json()
    assert d["source"] == "claude" and "[I99]" not in d["sections"][1]["body"]
    assert any("non-existent" in n for n in d["validation_notes"])

    llm_mod.set_llm(FakeLLM({"LLMExplanation": {
        "nct_id": "NCT04646759", "what_is_tested": "x", "why_might_fit": "You are eligible [I1].",
        "what_to_check": "Nothing [E1].", "questions_for_team": []}}))
    d = (await api.post("/api/trials/NCT04646759/explain", json={"mode": "patient"})).json()
    assert d["source"] == "rules" and "overconfident" in d["validation_notes"][0]


async def test_compare(api):
    ids = ["NCT04646759", "NCT07263425"]
    d = (await api.post("/api/trials/compare", json={"nct_ids": ids})).json()
    fields = [r["field"] for r in d["rows"]]
    assert "Study phase" in fields and "Official study link" in fields and "effectiveness" in d["note"]
    assert (await api.post("/api/trials/compare", json={"nct_ids": ["NCT04646759"]})).status_code == 422


async def test_followup_answer_updates_profile(api):
    q = {"id": "q1", "question": "Did the disease progress after osimertinib?", "why": "", "affected_trials": [],
         "priority": 1, "patch": {"type": "set_progression", "treatment": "osimertinib"}}
    prof = json.loads(DEMOS[1]["profile"].model_dump_json())
    r = await api.post("/api/patients/answer", json={"profile": prof, "question": q, "answer": "yes"})
    tx = r.json()["history"]["prior_treatments"][0]
    assert tx["progression"] == "yes" and tx["source"] == "patient_provided"
    r = await api.post("/api/patients/answer", json={"profile": prof, "question": q, "answer": "not_sure"})
    assert r.json()["history"]["prior_treatments"][0]["progression"] == "unknown"


async def test_parse_is_not_logged_and_errors_do_not_echo_input(api, caplog):
    caplog.set_level(logging.INFO)
    secret = "My rare-condition narrative 4471"
    r = await api.post("/api/patients/parse", json={"narrative": secret + " breast cancer, 50 years old"})
    assert r.status_code == 200 and r.json()["extraction_method"] == "rules"
    assert secret not in caplog.text
    r = await api.post("/api/patients/parse", json={"narrative": "x" * 5000 + secret})
    assert r.status_code == 422 and secret not in r.text


async def test_demo_profiles_are_marked_fictional(api):
    d = (await api.get("/api/demo/profiles")).json()
    assert len(d) >= 5 and all(p["profile"]["is_demo"] for p in d)
