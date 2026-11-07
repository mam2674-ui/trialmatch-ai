"""Deterministic eligibility rules: ages, biomarkers, prior therapy, stage, negation, conditional criteria."""

from app.schemas.patient import Biomarker, Fact, PatientProfile, Treatment
from app.schemas.trial import NormalizedTrial
from app.services.eligibility_rules import criterion_rules, structured_checks
from app.services.trial_normalizer import split_criteria


def P(**kw) -> PatientProfile:
    p = PatientProfile()
    d = p.demographics
    if "age" in kw:
        d.age_years = Fact(value=kw["age"])
    if "sex" in kw:
        d.sex = Fact(value=kw["sex"])
    if "stage" in kw:
        p.diagnosis.stage = Fact(value=kw["stage"])
    if "metastatic" in kw:
        p.diagnosis.metastatic = Fact(value=kw["metastatic"])
    p.diagnosis.biomarkers = [Biomarker(name=n, status=s) for n, s in kw.get("markers", [])]
    p.history.prior_treatments = [Treatment(name=n, status="completed") for n in kw.get("tx", [])]
    if "ecog" in kw:
        p.history.ecog_performance_status = Fact(value=kw["ecog"])
    if "preg" in kw:
        p.history.pregnant_or_breastfeeding = Fact(value=kw["preg"])
    return p


def T(text="", **kw) -> NormalizedTrial:
    return NormalizedTrial(nct_id="NCT00000001", brief_title="t", criteria=split_criteria(text), **kw)


def rules(p, text):
    return {k: (o.result.assessment, o.result.is_blocker) for k, o in criterion_rules(p, T(text)).items()}


# --- structured ---

def test_age_boundaries():
    t = T(min_age_years=18, max_age_years=65, minimum_age="18 Years", maximum_age="65 Years", overall_status="RECRUITING")
    get = lambda age: next(r for r in structured_checks(P(age=age), t) if r.criterion_id == "AGE").assessment  # noqa: E731
    assert get(18) == "MET" and get(65) == "MET" and get(17) == "NOT_MET" and get(66) == "NOT_MET"


def test_unknown_age_is_unknown_not_met():
    t = T(min_age_years=18, minimum_age="18 Years", overall_status="RECRUITING")
    r = next(r for r in structured_checks(P(), t) if r.criterion_id == "AGE")
    assert r.assessment == "UNKNOWN" and not r.is_blocker and r.needs_info


def test_sex_and_status():
    t = T(sex="FEMALE", overall_status="COMPLETED")
    res = {r.criterion_id: r for r in structured_checks(P(sex="male"), t)}
    assert res["SEX"].assessment == "NOT_MET" and res["SEX"].is_blocker
    assert res["STATUS"].assessment == "NOT_MET" and res["STATUS"].is_blocker
    t2 = T(sex="ALL", overall_status="NOT_YET_RECRUITING")
    res2 = {r.criterion_id: r for r in structured_checks(P(), t2)}
    assert res2["SEX"].assessment == "NOT_APPLICABLE" and res2["STATUS"].assessment == "MET"


# --- biomarkers ---

def test_known_incompatible_biomarker_blocks():
    assert rules(P(markers=[("HER2", "negative")]), "Inclusion Criteria:\n* HER2-positive breast cancer (IHC 3+ or ISH+)") \
        == {"I1": ("NOT_MET", True)}


def test_biomarker_alternatives_are_not_definitive():
    assert rules(P(markers=[("HER2", "negative")]), "Inclusion Criteria:\n* HER2-positive or HER2-low disease") == {}


def test_triple_negative_requirement_blocks_her2_positive():
    assert rules(P(markers=[("HER2", "positive")]), "Inclusion Criteria:\n* Diagnosis of triple-negative breast cancer") \
        == {"I1": ("NOT_MET", True)}


def test_biomarker_negation_in_criterion():
    # "without EGFR mutation" as an exclusion does not apply to an EGFR-mutant patient.
    assert rules(P(markers=[("EGFR", "mutated")]), "Exclusion Criteria:\n* Patients without EGFR mutation") \
        == {"E1": ("NOT_MET", False)}
    assert rules(P(markers=[("EGFR", "mutated")]), "Exclusion Criteria:\n* Known EGFR mutation") == {"E1": ("MET", True)}


def test_biomarker_in_nested_subitem_or_conditional_is_not_definitive():
    nested = "Inclusion Criteria:\n* One of the following subtypes:\n\n  * Triple negative breast cancer\n  * HER2-positive"
    assert rules(P(markers=[("HER2", "positive")]), nested) == {}
    cond = "Inclusion Criteria:\n* Patients with ER-low, HER2-negative BC must be ineligible for endocrine therapy"
    assert rules(P(markers=[("HER2", "positive")]), cond) == {}
    assert rules(P(markers=[("ER", "negative")]), "Inclusion Criteria:\n* If assigned male at birth with ER+ breast cancer, must use a GnRH agonist") == {}


def test_lowercase_short_markers_not_misread():
    # "er" inside ordinary words / lowercase must not be read as estrogen receptor.
    assert rules(P(markers=[("ER", "negative")]), "Inclusion Criteria:\n* Patients older than 18 positive for consent") == {}


# --- prior therapy ---

def test_excluded_prior_treatment():
    assert rules(P(tx=["osimertinib"]), "Exclusion Criteria:\n* Prior treatment with osimertinib") == {"E1": ("MET", True)}


def test_excluded_prior_treatment_by_drug_class():
    assert rules(P(tx=["osimertinib"]), "Exclusion Criteria:\n* Prior therapy with an EGFR tyrosine kinase inhibitor") \
        == {"E1": ("MET", True)}


def test_time_window_exclusion_is_not_definitive():
    assert rules(P(tx=["osimertinib"]), "Exclusion Criteria:\n* Osimertinib received within 14 days before first dose") == {}


def test_generic_treatment_categories_never_block():
    assert rules(P(tx=["chemotherapy", "surgery"]), "Exclusion Criteria:\n* Receipt of adjuvant chemotherapy\n* Prior major surgery") == {}


def test_treatment_naive_requirement():
    assert rules(P(tx=["pembrolizumab"]), "Inclusion Criteria:\n* No prior immune checkpoint inhibitor therapy") \
        == {"I1": ("NOT_MET", True)}


def test_prior_exposure_does_not_establish_progression():
    # Requirement to have progressed: rules must not mark it MET from exposure alone.
    assert rules(P(tx=["osimertinib"]), "Inclusion Criteria:\n* Progressed following an EGFR tyrosine kinase inhibitor") == {}


# --- stage ---

def test_stage_mismatch():
    assert rules(P(stage="Stage II"), "Inclusion Criteria:\n* Metastatic breast cancer") == {"I1": ("NOT_MET", True)}
    assert rules(P(stage="Stage IV"), "Inclusion Criteria:\n* Stage I-III breast cancer") == {"I1": ("NOT_MET", True)}
    assert rules(P(stage="Stage IIB"), "Inclusion Criteria:\n* Stage II or III disease") == {}


def test_stage_negation_is_respected():
    assert rules(P(stage="Stage II"), "Inclusion Criteria:\n* Participants must not have metastatic disease (M1)") \
        == {"I1": ("MET", False)}
    assert rules(P(metastatic=True), "Inclusion Criteria:\n* Participants must not have metastatic disease (M1)") \
        == {"I1": ("NOT_MET", True)}


def test_metastatic_setting_phrase_is_not_a_requirement():
    assert rules(P(stage="Stage II"), "Inclusion Criteria:\n* DOSE EXPANSION COHORT: 0-1 prior lines in the metastatic setting") == {}


# --- other ---

def test_ecog_and_alternatives():
    assert rules(P(ecog=2), "Inclusion Criteria:\n* ECOG performance status 0-1") == {"I1": ("NOT_MET", True)}
    assert rules(P(ecog=1), "Inclusion Criteria:\n* ECOG performance status 0-1") == {"I1": ("MET", False)}
    assert rules(P(ecog=2), "Inclusion Criteria:\n* ECOG 0-1 or Karnofsky ≥ 70") == {}


def test_pregnancy_exclusion():
    assert rules(P(sex="male"), "Exclusion Criteria:\n* Pregnant or breastfeeding") == {"E1": ("NOT_APPLICABLE", False)}
    assert rules(P(sex="female", preg=True), "Exclusion Criteria:\n* Pregnant or breastfeeding") == {"E1": ("MET", True)}
    assert rules(P(sex="female"), "Exclusion Criteria:\n* Pregnant or breastfeeding") == {}  # unknown stays unknown


def test_menopause_definition_ages_are_ignored():
    text = ("Inclusion Criteria:\n* Premenopausal women must have a negative pregnancy test. Not needed if:\n\n"
            "  * Age > 60 years")
    assert rules(P(age=42), text) == {}


# --- regressions from auditing live results (real criterion wording) ---

def test_ecog_phrasings_from_real_records():
    from app.services.eligibility_rules import parse_ecog_range
    cases = {
        "Eastern Cooperative Oncology Group (ECOG) Performance Status of 0 to 1.": (0, 1),
        "Participant must have eastern cooperative oncology group (ECOG) status of 0 or 1": (0, 1),
        "ECOG score of 0, 1, or 2.": (0, 2),
        "Eastern Cooperative Oncology Group (ECOG) performance status of <= 0 or 1 and a life expectancy of >= 3 months.": (0, 1),
        "Participants must have an Eastern Cooperative Oncology Group performance status (ECOG-PS) less than or equal to (<=) 1": (0, 1),
        "ECOG performance status of 0-1. For subjects with primary CNS tumors, KPS score ≥70.": (0, 1),
    }
    for text, rng in cases.items():
        assert parse_ecog_range(text)[:2] == rng, text
    assert rules(P(ecog=1), "Inclusion Criteria:\n* ECOG Performance Status of 0 to 1") == {"I1": ("MET", False)}


def test_stage_list_with_or():
    assert rules(P(stage="Stage IV"), "Inclusion Criteria:\n* Confirmed diagnosis of Stage IIIB, IIIC, or IV sqNSCLC") == {}


def test_cohort_specific_criteria_are_conditional():
    text = "Inclusion Criteria:\n* Participants in Cohorts 5 and 11 must present with unresectable Stage III NSCLC"
    assert rules(P(stage="Stage IV"), text) == {}


def test_drug_mentioned_outside_prior_therapy_phrase():
    text = ("Exclusion Criteria:\n* History of clinically significant cardiovascular disease, including QTc prolongation "
            "considered related to treatment by the investigator when combined with agents such as lazertinib")
    assert rules(P(tx=["osimertinib"]), text) == {}


def test_variant_specific_biomarker_criteria():
    p = P(markers=[("EGFR", "mutated")])
    p.diagnosis.biomarkers[0].detail = "exon 19 deletion"
    assert rules(p, "Exclusion Criteria:\n* Previously documented EGFR Exon 20 insertion mutations") == {}
    assert rules(p, "Exclusion Criteria:\n* Known EGFR exon 19 deletion") == {"E1": ("MET", True)}
    unknown_variant = P(markers=[("EGFR", "mutated")])
    assert rules(unknown_variant, "Exclusion Criteria:\n* Known EGFR exon 20 insertion") == {}


def test_biomarker_met_only_when_nothing_else_is_required():
    her2 = P(markers=[("HER2", "positive")])
    assert rules(her2, "Inclusion Criteria:\n* HER2-positive breast cancer (IHC 3+ or ISH+)") == {"I1": ("MET", False)}
    assert rules(her2, "Inclusion Criteria:\n* Women with HER2-positive breast cancer") == {}
    egfr = P(markers=[("EGFR", "mutated")])
    assert rules(egfr, "Inclusion Criteria:\n* Treatment-naive advanced EGFR-mutant NSCLC") == {}


def test_current_medication_exclusion():
    p = P()
    p.history.current_medications = [Fact(value="empagliflozin")]
    assert rules(p, "Exclusion Criteria:\n* Current treatment with an SGLT2 inhibitor") == {"E1": ("MET", True)}
