"""Small curated terminology layer: biomarker synonyms, lab units, therapy classes, plain-language glossary.

Deliberately small and explicit. It is used for normalization and deterministic rules, not for
inferring facts the patient did not provide.
"""

from __future__ import annotations

import re

BIOMARKER_SYNONYMS: dict[str, list[str]] = {
    "HER2": ["her2", "her-2", "her 2", "erbb2", "her2/neu", "neu"],
    "ER": ["er", "estrogen receptor", "oestrogen receptor"],
    "PR": ["pr", "pgr", "progesterone receptor"],
    "EGFR": ["egfr"],
    "ALK": ["alk"],
    "ROS1": ["ros1"],
    "KRAS": ["kras"],
    "BRAF": ["braf"],
    "MET": ["met"],
    "RET": ["ret"],
    "NTRK": ["ntrk"],
    "PD-L1": ["pd-l1", "pdl1", "pd l1"],
    "BRCA1": ["brca1"],
    "BRCA2": ["brca2"],
    "PIK3CA": ["pik3ca"],
    "ESR1": ["esr1"],
    "MSI-H": ["msi-h", "msi high", "microsatellite instability-high", "dmmr"],
    "LRRK2": ["lrrk2"],
    "GBA": ["gba", "gba1"],
    "CFTR": ["cftr"],
    "HbA1c": ["hba1c", "a1c", "hemoglobin a1c", "glycated hemoglobin"],
}

_SYN_LOOKUP = {syn: canon for canon, syns in BIOMARKER_SYNONYMS.items() for syn in syns}


def normalize_biomarker_name(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip().lower())
    return _SYN_LOOKUP.get(key, name.strip())


def biomarker_pattern(canonical: str) -> str:
    """Regex alternation matching any synonym of a canonical biomarker as a whole word."""
    syns = BIOMARKER_SYNONYMS.get(canonical, [canonical.lower()])
    # Very short ambiguous synonyms ("er", "pr", "met", "ret", "neu") are only matched in uppercase
    # contexts by the caller; here we exclude them for robustness in free text.
    usable = [s for s in syns if len(s) > 3 or s in ("alk", "her2")] or [canonical.lower()]
    if canonical in ("ER", "PR", "MET", "RET"):
        usable = [canonical.lower()] + [s for s in syns if len(s) > 3]
    return r"(?<![a-z0-9])(?:" + "|".join(re.escape(s) for s in sorted(set(usable), key=len, reverse=True)) + r")(?![a-z0-9])"


# Labs: canonical name -> {accepted unit (lowercase): conversion factor to canonical unit}, canonical unit,
# and a physiologically plausible range in canonical units (rejects obvious typos, not clinical judgment).
LABS: dict[str, dict] = {
    "hemoglobin": {"aliases": ["hgb", "hb", "haemoglobin"], "unit": "g/dL",
                   "conv": {"g/dl": 1.0, "g/l": 0.1, "mmol/l": 1.611}, "range": (2, 25)},
    "platelets": {"aliases": ["plt", "platelet count"], "unit": "10^9/L",
                  "conv": {"10^9/l": 1.0, "x10^9/l": 1.0, "k/ul": 1.0, "10^3/ul": 1.0, "/ul": 0.001}, "range": (1, 2000)},
    "anc": {"aliases": ["absolute neutrophil count", "neutrophils"], "unit": "10^9/L",
            "conv": {"10^9/l": 1.0, "x10^9/l": 1.0, "k/ul": 1.0, "10^3/ul": 1.0, "/ul": 0.001, "cells/ul": 0.001},
            "range": (0, 100)},
    "creatinine": {"aliases": ["serum creatinine", "cr"], "unit": "mg/dL",
                   "conv": {"mg/dl": 1.0, "umol/l": 1 / 88.42, "µmol/l": 1 / 88.42}, "range": (0.1, 20)},
    "egfr_renal": {"aliases": ["egfr (renal)", "gfr", "creatinine clearance", "crcl"], "unit": "mL/min/1.73m2",
                   "conv": {"ml/min/1.73m2": 1.0, "ml/min/1.73 m2": 1.0, "ml/min": 1.0}, "range": (1, 200)},
    "total_bilirubin": {"aliases": ["bilirubin", "tbil", "total bilirubin"], "unit": "mg/dL",
                        "conv": {"mg/dl": 1.0, "umol/l": 1 / 17.1, "µmol/l": 1 / 17.1}, "range": (0, 50)},
    "alt": {"aliases": ["sgpt", "alanine aminotransferase"], "unit": "U/L", "conv": {"u/l": 1.0, "iu/l": 1.0},
            "range": (0, 10000)},
    "ast": {"aliases": ["sgot", "aspartate aminotransferase"], "unit": "U/L", "conv": {"u/l": 1.0, "iu/l": 1.0},
            "range": (0, 10000)},
    "hba1c": {"aliases": ["a1c", "hemoglobin a1c", "glycated hemoglobin"], "unit": "%",
              "conv": {"%": 1.0, "percent": 1.0}, "range": (3, 20)},
    "lvef": {"aliases": ["ejection fraction", "ef", "left ventricular ejection fraction"], "unit": "%",
             "conv": {"%": 1.0, "percent": 1.0}, "range": (5, 90)},
    "bmi": {"aliases": ["body mass index"], "unit": "kg/m2", "conv": {"kg/m2": 1.0, "kg/m^2": 1.0}, "range": (10, 90)},
}
_LAB_LOOKUP = {a: k for k, v in LABS.items() for a in [k, *v["aliases"]]}


def normalize_lab(name: str, unit: str, value: float) -> tuple[str, str]:
    """Validate a lab's unit against the curated list. Unknown labs are allowed but kept verbatim."""
    key = _LAB_LOOKUP.get(name.strip().lower())
    if key is None:
        return name.strip(), unit.strip()
    spec = LABS[key]
    u = unit.strip().lower().replace(" ", "") if unit else ""
    conv = {k.replace(" ", ""): f for k, f in spec["conv"].items()}
    if u not in conv:
        raise ValueError(f"unit '{unit}' is not a recognized unit for {key} (expected e.g. {spec['unit']})")
    lo, hi = spec["range"]
    if not lo <= value * conv[u] <= hi:
        raise ValueError(f"{key} value {value} {unit} is outside a physiologically plausible range")
    return key, unit.strip()


# Therapy classes for deterministic prior-therapy rules. Membership is factual drug classification.
THERAPY_CLASSES: dict[str, list[str]] = {
    "EGFR tyrosine kinase inhibitor": ["osimertinib", "erlotinib", "gefitinib", "afatinib", "dacomitinib",
                                       "lazertinib", "egfr tki", "egfr-tki", "egfr tyrosine kinase inhibitor"],
    "ALK inhibitor": ["alectinib", "crizotinib", "lorlatinib", "brigatinib", "ceritinib"],
    "anti-HER2 therapy": ["trastuzumab", "pertuzumab", "trastuzumab deruxtecan", "t-dxd", "t-dm1",
                          "ado-trastuzumab emtansine", "tucatinib", "lapatinib", "neratinib", "pyrotinib",
                          "margetuximab", "herceptin"],
    "immune checkpoint inhibitor": ["pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "ipilimumab",
                                    "cemiplimab", "dostarlimab", "tremelimumab", "pd-1", "pd-l1", "anti-pd-1",
                                    "checkpoint inhibitor", "immunotherapy"],
    "CDK4/6 inhibitor": ["palbociclib", "ribociclib", "abemaciclib"],
    "anthracycline": ["doxorubicin", "epirubicin", "daunorubicin", "anthracycline"],
    "taxane": ["paclitaxel", "docetaxel", "nab-paclitaxel", "taxane"],
    "platinum chemotherapy": ["cisplatin", "carboplatin", "oxaliplatin", "platinum"],
    "levodopa": ["levodopa", "carbidopa/levodopa", "l-dopa", "sinemet"],
    "SGLT2 inhibitor": ["empagliflozin", "dapagliflozin", "canagliflozin", "ertugliflozin", "sglt2"],
    "GLP-1 receptor agonist": ["semaglutide", "liraglutide", "dulaglutide", "exenatide", "tirzepatide", "glp-1"],
    "insulin": ["insulin", "insulin glargine", "insulin lispro", "insulin aspart"],
    "metformin": ["metformin"],
}


def therapy_classes_for(drug: str) -> list[str]:
    d = drug.strip().lower()
    return [cls for cls, members in THERAPY_CLASSES.items() if any(m == d or m in d for m in members)]


# Plain-language glossary. Definitions are written for this project, not generated per request.
GLOSSARY: dict[str, str] = {
    "biomarker": "A measurable feature of your body or tumor (for example a gene mutation or a protein) that can help doctors choose treatments or decide who can join a study.",
    "randomized": "Participants are assigned to study groups by chance, like a coin flip, so the groups can be compared fairly.",
    "placebo": "An inactive substance that looks like the study treatment. It helps researchers tell whether effects come from the treatment itself.",
    "double-blind": "Neither the participants nor the study doctors know who receives which treatment until the study ends.",
    "open-label": "Everyone, including participants, knows which treatment is being given.",
    "progression-free survival": "How long people live without their disease getting worse, measured from the start of treatment.",
    "overall survival": "How long people in the study live, measured from the start of treatment.",
    "immunotherapy": "Treatment that helps your immune system recognize and attack disease, such as cancer.",
    "phase 1": "An early study that mainly tests safety and dosing, usually in a small group of people.",
    "phase 2": "A study that tests whether a treatment shows signs of working and continues to study safety.",
    "phase 3": "A larger study comparing a new treatment with the current standard treatment.",
    "metastatic": "Cancer that has spread from where it started to other parts of the body.",
    "ecog": "A 0–5 scale doctors use to describe how well someone can carry out daily activities (0 = fully active).",
    "her2": "A protein that can drive some breast and stomach cancers. 'HER2-positive' tumors have high levels of it.",
    "egfr": "A gene that, when mutated, can drive some lung cancers. Certain targeted drugs block it.",
    "tyrosine kinase inhibitor": "A type of targeted medicine that blocks specific signals cancer cells use to grow.",
    "adjuvant": "Treatment given after the main treatment (often surgery) to lower the chance of the disease coming back.",
    "neoadjuvant": "Treatment given before the main treatment (often surgery), for example to shrink a tumor.",
    "inclusion criteria": "Requirements a person must meet to join a study.",
    "exclusion criteria": "Conditions that would prevent a person from joining a study, usually for safety reasons.",
    "hba1c": "A blood test that reflects average blood sugar over about the past three months.",
    "antibody-drug conjugate": "A targeted medicine that attaches a cell-killing drug to an antibody so it is delivered to specific cells.",
}


def glossary_terms_in(text: str) -> dict[str, str]:
    low = text.lower()
    return {t: d for t, d in GLOSSARY.items() if re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", low)}
