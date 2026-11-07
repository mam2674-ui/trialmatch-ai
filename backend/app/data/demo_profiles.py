"""Fictional demo patients. None of these describe real people.

Each has a narrative (for the AI parser) and an equivalent pre-structured profile so the demo works even
when Claude is not configured. Structured values are marked patient_provided because they represent what
a user would enter in the form.
"""

from app.schemas.patient import (
    Biomarker, Demographics, Diagnosis, Fact, Location, MedicalHistory, PatientProfile, Preferences, Treatment,
)


def _f(v):
    return Fact(value=v, source="patient_provided")


DEMOS = [
    {
        "id": "breast-her2",
        "title": "Early HER2-positive breast cancer",
        "challenge": "Molecular markers + completed adjuvant therapy; must not confuse 'not started immunotherapy' with prior immunotherapy.",
        "narrative": ("I'm a 42-year-old woman living in Boston, MA. I was diagnosed with stage II HER2-positive, "
                      "ER-negative breast cancer. I've completed surgery and chemotherapy but haven't started "
                      "immunotherapy. I'm interested in clinical trials within 100 miles of Boston."),
        "profile": PatientProfile(
            is_demo=True,
            demographics=Demographics(age_years=_f(42), sex=_f("female"),
                                      location=Location(city="Boston", state="MA", country="United States", source="patient_provided"),
                                      travel_radius_miles=_f(100)),
            diagnosis=Diagnosis(primary_condition=_f("breast cancer"), stage=_f("Stage II"), metastatic=_f(False),
                                biomarkers=[Biomarker(name="HER2", status="positive"), Biomarker(name="ER", status="negative")]),
            history=MedicalHistory(prior_treatments=[Treatment(name="surgery", category="surgery", status="completed"),
                                                     Treatment(name="chemotherapy", category="chemotherapy", status="completed")]),
            preferences=Preferences(willing_to_travel=True),
        ),
    },
    {
        "id": "nsclc-egfr",
        "title": "Metastatic EGFR-mutant lung cancer after osimertinib",
        "challenge": "Prior targeted therapy: osimertinib exposure is known, but progression is not stated and must not be inferred.",
        "narrative": ("58-year-old male in Chicago, IL with metastatic non-small cell lung cancer (adenocarcinoma), "
                      "EGFR exon 19 deletion, previously treated with osimertinib. ECOG 1. Willing to travel up to 300 miles."),
        "profile": PatientProfile(
            is_demo=True,
            demographics=Demographics(age_years=_f(58), sex=_f("male"),
                                      location=Location(city="Chicago", state="IL", country="United States", source="patient_provided"),
                                      travel_radius_miles=_f(300)),
            diagnosis=Diagnosis(primary_condition=_f("non-small cell lung cancer"), histology=_f("adenocarcinoma"),
                                stage=_f("Stage IV"), metastatic=_f(True),
                                biomarkers=[Biomarker(name="EGFR", status="mutated", detail="exon 19 deletion")]),
            history=MedicalHistory(prior_treatments=[Treatment(name="osimertinib", category="targeted therapy",
                                                               status="completed", progression="unknown")],
                                   ecog_performance_status=_f(1)),
            preferences=Preferences(willing_to_travel=True),
        ),
    },
    {
        "id": "parkinsons",
        "title": "Early Parkinson's disease",
        "challenge": "Neurology trials often hinge on disease duration, Hoehn & Yahr stage and medication status that the patient may not know.",
        "narrative": ("I'm a 67-year-old man in Seattle, WA. I was diagnosed with Parkinson's disease about two years ago. "
                      "I take carbidopa/levodopa. I'd consider trials within 150 miles."),
        "profile": PatientProfile(
            is_demo=True,
            demographics=Demographics(age_years=_f(67), sex=_f("male"),
                                      location=Location(city="Seattle", state="WA", country="United States", source="patient_provided"),
                                      travel_radius_miles=_f(150)),
            diagnosis=Diagnosis(primary_condition=_f("Parkinson's disease")),
            history=MedicalHistory(current_medications=[_f("carbidopa/levodopa")]),
        ),
    },
    {
        "id": "t2d-cvd",
        "title": "Type 2 diabetes with cardiovascular disease",
        "challenge": "Lab-value thresholds (HbA1c) and comorbidity-based inclusion; units must be validated.",
        "narrative": ("61-year-old woman in Houston, TX with type 2 diabetes for 12 years and coronary artery disease "
                      "(stent placed in 2022). Taking metformin and empagliflozin. My last HbA1c was 8.4%. "
                      "Looking for trials within 50 miles."),
        "profile": PatientProfile(
            is_demo=True,
            demographics=Demographics(age_years=_f(61), sex=_f("female"),
                                      location=Location(city="Houston", state="TX", country="United States", source="patient_provided"),
                                      travel_radius_miles=_f(50)),
            diagnosis=Diagnosis(primary_condition=_f("type 2 diabetes")),
            history=MedicalHistory(
                current_medications=[_f("metformin"), _f("empagliflozin")],
                comorbidities=[_f("coronary artery disease (stent placed in 2022)")],
                labs=[{"name": "HbA1c", "value": 8.4, "unit": "%"}],
            ),
        ),
    },
    {
        "id": "cystic-fibrosis",
        "title": "Cystic fibrosis (rare inherited disorder)",
        "challenge": "Genotype-specific trials (e.g. F508del) and pediatric/adult age bands; genotype detail is often missing.",
        "narrative": ("My 24-year-old son has cystic fibrosis. He has one F508del CFTR mutation; we're not sure about "
                      "the second variant. We live in Denver, CO and can travel within 500 miles."),
        "profile": PatientProfile(
            is_demo=True,
            demographics=Demographics(age_years=_f(24), sex=_f("male"),
                                      location=Location(city="Denver", state="CO", country="United States", source="patient_provided"),
                                      travel_radius_miles=_f(500)),
            diagnosis=Diagnosis(primary_condition=_f("cystic fibrosis"),
                                biomarkers=[Biomarker(name="CFTR", status="mutated", detail="one F508del allele; second variant unknown")]),
        ),
    },
]
