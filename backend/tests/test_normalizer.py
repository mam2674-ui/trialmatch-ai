"""Normalization of real ClinicalTrials.gov records, missing fields, and eligibility-text splitting."""

import copy

from app.services.trial_normalizer import normalize_study, parse_age_years, split_criteria
from tests.conftest import load_fixture


def test_real_record_fields_are_copied_not_invented():
    raw = load_fixture("search_breast_her2.json")["studies"][0]
    t = normalize_study(raw)
    ps = raw["protocolSection"]
    assert t.nct_id == ps["identificationModule"]["nctId"]
    assert t.brief_title == ps["identificationModule"]["briefTitle"]
    assert t.overall_status == ps["statusModule"]["overallStatus"]
    assert t.phases == ps["designModule"].get("phases", [])
    assert t.last_update_post_date == ps["statusModule"]["lastUpdatePostDateStruct"]["date"]
    assert t.url == f"https://clinicaltrials.gov/study/{t.nct_id}"
    assert len(t.locations) == len(ps["contactsLocationsModule"].get("locations", []))
    for site, src in zip(t.locations, ps["contactsLocationsModule"]["locations"]):
        assert site.lat == (src.get("geoPoint") or {}).get("lat")  # coordinates only from the API
    assert t.criteria and {c.kind for c in t.criteria} >= {"inclusion", "exclusion"}


def test_every_criterion_text_comes_from_source():
    for name in ["search_breast_her2.json", "search_nsclc_egfr.json", "search_parkinson.json", "search_cf.json"]:
        for raw in load_fixture(name)["studies"]:
            t = normalize_study(raw)
            src = " ".join((t.eligibility_text or "").split())
            for c in t.criteria:
                first_line = " ".join(c.text.split("\n")[0].split())
                assert first_line in src, (t.nct_id, c.criterion_id)


def test_missing_fields_stay_missing():
    raw = copy.deepcopy(load_fixture("search_cf.json")["studies"][0])
    ps = raw["protocolSection"]
    for mod in ["contactsLocationsModule", "descriptionModule", "designModule", "armsInterventionsModule"]:
        ps.pop(mod, None)
    ps["eligibilityModule"] = {}
    t = normalize_study(raw)
    assert t.locations == [] and t.central_contacts == [] and t.brief_summary is None
    assert t.phases == [] and t.interventions == [] and t.criteria == []
    assert t.min_age_years is None and t.sex is None and t.healthy_volunteers is None


def test_age_parsing():
    assert parse_age_years("18 Years") == 18
    assert parse_age_years("6 Months") == 0.5
    assert parse_age_years("N/A") is None and parse_age_years(None) is None


def test_split_standard_bullets_and_nesting():
    text = ("Inclusion Criteria:\n\n* Age ≥ 18\n* Must be postmenopausal\n\n  * NOTE: defined as:\n\n    * Age ≥ 60 years\n"
            "* ECOG 0\\-1\n\nExclusion Criteria:\n\n1. Prior osimertinib\n2. Pregnant")
    cs = split_criteria(text)
    assert [c.criterion_id for c in cs] == ["I1", "I2", "I3", "E1", "E2"]
    assert "Age ≥ 60 years" in cs[1].text  # nested sub-items stay with their parent
    assert cs[2].text == "ECOG 0-1"  # markdown escapes removed


def test_split_fused_and_bulleted_headings():
    cs = split_criteria("Inclusion Criteria:The subjects must meet all:\n\n* HER2 positive\n\n* Exclusion Criteria:\n* Pregnant")
    assert [(c.criterion_id, c.text) for c in cs] == [("I1", "The subjects must meet all:"), ("I2", "HER2 positive"),
                                                      ("E1", "Pregnant")]


def test_split_without_headings_is_unclassified():
    cs = split_criteria("Adults with asthma.\n\nNon-smokers.")
    assert [c.kind for c in cs] == ["unclassified", "unclassified"]


def test_record_update_changes_status(db):
    from app.services.trial_repository import get_cached_trials, upsert_study
    raw = copy.deepcopy(load_fixture("search_cf.json")["studies"][0])
    nct = raw["protocolSection"]["identificationModule"]["nctId"]
    upsert_study(db, raw)
    db.commit()
    raw["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
    raw["protocolSection"]["eligibilityModule"]["eligibilityCriteria"] = "Inclusion Criteria:\n* Only one now"
    upsert_study(db, raw)
    db.commit()
    t = get_cached_trials(db, [nct])[nct]
    assert t.overall_status == "COMPLETED"
    assert [c.text for c in t.criteria] == ["Only one now"]
