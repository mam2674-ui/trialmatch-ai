"""Hybrid engine: Claude output validation, hallucination handling, rule precedence, categories."""

import pytest

from app.schemas.patient import Biomarker, Conflict, Fact, PatientProfile, Treatment
from app.schemas.trial import NormalizedTrial
from app.services.eligibility_engine import assess_trial, categorize
from app.services.llm import LLMUnavailable
from app.services.trial_normalizer import split_criteria
from tests.conftest import FakeLLM

EGFR_TRIAL = NormalizedTrial(
    nct_id="NCT00000042", brief_title="EGFR study", overall_status="RECRUITING", sex="ALL", min_age_years=18,
    minimum_age="18 Years",
    criteria=split_criteria(
        "Inclusion Criteria:\n* Histologically confirmed advanced NSCLC with documented activating EGFR mutations.\n"
        "* Participants must have progressed following an EGFR tyrosine kinase inhibitor.\n"
        "Exclusion Criteria:\n* Symptomatic brain metastases"),
)


def egfr_patient() -> PatientProfile:
    p = PatientProfile()
    p.demographics.age_years = Fact(value=58)
    p.demographics.sex = Fact(value="male")
    p.diagnosis.primary_condition = Fact(value="non-small cell lung cancer")
    p.diagnosis.metastatic = Fact(value=True)
    p.diagnosis.biomarkers = [Biomarker(name="EGFR", status="mutated", detail="exon 19 deletion")]
    p.history.prior_treatments = [Treatment(name="osimertinib", status="completed")]
    return p


def good_response(nct="NCT00000042", **over):
    r = {
        "nct_id": nct,
        "criteria": [
            {"criterion_id": "I1", "assessment": "MET",
             "trial_evidence": "advanced NSCLC with documented activating EGFR mutations",
             "patient_evidence": ["non-small cell lung cancer", "EGFR mutated exon 19 deletion"],
             "explanation": "Diagnosis and EGFR mutation match.", "impact": "high"},
            {"criterion_id": "I2", "assessment": "UNKNOWN",
             "trial_evidence": "must have progressed following an EGFR tyrosine kinase inhibitor",
             "patient_evidence": ["osimertinib"], "explanation": "Prior osimertinib is reported but progression is not.",
             "unknown_reason": "missing_patient_info", "impact": "high",
             "question": "Did the cancer grow while on or after osimertinib?"},
            {"criterion_id": "E1", "assessment": "UNKNOWN", "trial_evidence": "Symptomatic brain metastases",
             "patient_evidence": [], "explanation": "Brain metastases not reported.", "unknown_reason": "missing_patient_info",
             "impact": "high", "question": "Has the cancer spread to the brain?"},
        ],
        "profile_conflicts": [],
        "summary": "Diagnosis and EGFR mutation appear consistent [I1]. Progression after osimertinib must be confirmed [I2].",
    }
    r.update(over)
    return r


@pytest.mark.asyncio
async def test_spec_example_potential_match_confirmation_required():
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, FakeLLM({"LLMTrialAssessment": good_response()}))
    e = out["eligibility"]
    assert out["ai_status"] == "ok"
    assert e.category == "POTENTIAL_MATCH" and "confirmation" in e.headline
    crit = {c.criterion_id: c for c in out["criteria"]}
    assert crit["I1"].assessment == "MET" and crit["I1"].source == "claude"
    assert crit["I2"].assessment == "UNKNOWN" and crit["I2"].question  # progression is NOT inferred from exposure
    assert "[I2]" in e.explanation and e.explanation_source == "claude"


@pytest.mark.asyncio
async def test_hallucinated_patient_fact_is_downgraded():
    bad = good_response()
    bad["criteria"][1] = {**bad["criteria"][1], "assessment": "MET",
                          "patient_evidence": ["progressed on osimertinib in 2024"], "unknown_reason": None}
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, FakeLLM({"LLMTrialAssessment": bad}))
    i2 = next(c for c in out["criteria"] if c.criterion_id == "I2")
    assert i2.assessment == "UNKNOWN" and i2.patient_evidence == []
    assert any("not found in the profile" in n for n in i2.validation_notes)
    assert out["report"].unsupported_patient_claims == 1
    assert out["ai_status"] == "ok"  # one bad claim is downgraded; the rest of the analysis is kept


@pytest.mark.asyncio
async def test_widespread_hallucination_withholds_all_ai_output():
    bad = good_response()
    for c in bad["criteria"]:
        c["patient_evidence"] = ["invented fact about chemotherapy response"]
        c["assessment"] = "MET"
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, FakeLLM({"LLMTrialAssessment": bad}))
    assert out["ai_status"] == "validation_failed" and all(c.source != "claude" for c in out["criteria"])


@pytest.mark.asyncio
async def test_invented_criterion_and_misquote_are_rejected():
    bad = good_response()
    bad["criteria"].append({"criterion_id": "I9", "assessment": "NOT_MET", "trial_evidence": "Must live in Ohio",
                            "patient_evidence": [], "explanation": "Invented", "impact": "high"})
    bad["criteria"][0]["trial_evidence"] = "requires prior chemotherapy"  # not in source
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, FakeLLM({"LLMTrialAssessment": bad}))
    ids = [c.criterion_id for c in out["criteria"]]
    assert "I9" not in ids
    i1 = next(c for c in out["criteria"] if c.criterion_id == "I1")
    assert i1.trial_evidence is None and out["report"].unknown_criterion_ids == 1


@pytest.mark.asyncio
async def test_wrong_nct_is_rejected_then_withheld():
    llm = FakeLLM({"LLMTrialAssessment": [good_response(nct="NCT99999999"), good_response(nct="NCT99999999")]})
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, llm)
    assert len(llm.calls) == 2  # retried once
    assert out["ai_status"] == "validation_failed"
    assert all(c.source != "claude" for c in out["criteria"])
    assert out["eligibility"].category == "NEEDS_MORE_INFORMATION"


@pytest.mark.asyncio
async def test_retry_recovers_after_validation_failure():
    llm = FakeLLM({"LLMTrialAssessment": [good_response(nct="NCT11111111"), good_response()]})
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, llm)
    assert out["ai_status"] == "ok" and "failed validation" in llm.calls[1][1]


@pytest.mark.asyncio
async def test_summary_with_fake_citations_is_cleaned():
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, FakeLLM({"LLMTrialAssessment": good_response(
        summary="Matches [I1] and also [I77].")}))
    assert "[I77]" not in out["eligibility"].explanation and "[I1]" in out["eligibility"].explanation


@pytest.mark.asyncio
async def test_rule_overrides_model():
    p = egfr_patient()
    p.diagnosis.biomarkers = [Biomarker(name="EGFR", status="wild_type")]
    resp = good_response()
    resp["criteria"][0]["patient_evidence"] = ["non-small cell lung cancer"]
    out = await assess_trial(p, EGFR_TRIAL, FakeLLM({"LLMTrialAssessment": resp}))
    i1 = next(c for c in out["criteria"] if c.criterion_id == "I1")
    assert i1.source == "rule" and i1.assessment == "NOT_MET" and i1.is_blocker
    assert any("deterministic rule takes precedence" in n for n in i1.validation_notes)
    assert out["eligibility"].category == "POTENTIALLY_INELIGIBLE"


@pytest.mark.asyncio
async def test_claude_unavailable_never_fabricates():
    out = await assess_trial(egfr_patient(), EGFR_TRIAL, FakeLLM(error=LLMUnavailable("down")))
    assert out["ai_status"] == "unavailable"
    assert all(c.source in ("rule", "not_assessed") for c in out["criteria"])
    assert out["eligibility"].category == "NEEDS_MORE_INFORMATION"
    assert out["completeness"].not_assessed > 0


@pytest.mark.asyncio
async def test_not_recruiting_skips_ai_and_flags():
    t = EGFR_TRIAL.model_copy(update={"overall_status": "COMPLETED"})
    llm = FakeLLM({"LLMTrialAssessment": good_response()})
    out = await assess_trial(egfr_patient(), t, llm)
    assert llm.calls == [] and out["eligibility"].category == "POTENTIALLY_INELIGIBLE"


@pytest.mark.asyncio
async def test_conflicting_profile_information():
    p = egfr_patient()
    p.conflicts = [Conflict(field="age", description="Ages 58 and 62 both mentioned")]
    out = await assess_trial(p, EGFR_TRIAL, FakeLLM({"LLMTrialAssessment": good_response()}))
    assert out["eligibility"].category == "NEEDS_MORE_INFORMATION"
    assert "conflicting" in out["eligibility"].headline


def test_categorize_procedure():
    from app.schemas.match import CriterionResult

    def c(cid, a, kind="inclusion", impact="high", reason=None):
        blocker = (kind == "inclusion" and a == "NOT_MET") or (kind == "exclusion" and a == "MET")
        return CriterionResult(criterion_id=cid, kind=kind, criterion_text="x", assessment=a, is_blocker=blocker,
                               explanation="", impact=impact, unknown_reason=reason, source="claude")
    assert categorize([c("I1", "MET"), c("E1", "MET", "exclusion")], "ok", False)[0] == "POTENTIALLY_INELIGIBLE"
    assert categorize([c("I1", "UNKNOWN"), c("I2", "UNKNOWN"), c("I3", "MET")], "ok", False)[0] == "NEEDS_MORE_INFORMATION"
    assert categorize([c("I1", "MET"), c("I2", "UNKNOWN", reason="requires_clinical_judgment")], "ok", False)[0] \
        == "REQUIRES_CLINICAL_REVIEW"
    assert categorize([c("I1", "MET"), c("I2", "UNKNOWN", impact="routine", reason="requires_screening_test")], "ok",
                      False)[0] == "POTENTIAL_MATCH"
    # Unmet inclusion vs met exclusion are both blockers; unmet exclusion is not.
    assert categorize([c("I1", "MET"), c("E1", "NOT_MET", "exclusion")], "ok", False)[0] == "POTENTIAL_MATCH"


def test_followup_dedup_and_yes_no_only():
    from app.services.followup_service import _YES_NO_START, _similar
    assert _similar("Has your cancer spread to your brain or spine, and if so, is it stable?",
                    "Have you been told the cancer has spread to your brain, and if so, does it cause symptoms?")
    assert not _similar("Has your cancer spread to your brain?", "Did the disease grow after osimertinib?")
    assert not _YES_NO_START.match("When did you take your last dose of osimertinib?")
    assert _YES_NO_START.match("Besides osimertinib, have you received other drugs?")
