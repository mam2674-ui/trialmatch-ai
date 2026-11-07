"""Natural-language narrative -> structured PatientProfile.

Two extractors:
  * Claude (structured output). Every extracted value must carry a verbatim evidence quote. The
    verifier drops any value whose quote does not occur in the narrative, so the model cannot add
    facts that were not stated.
  * Deterministic rules (regex), used when Claude is unavailable. Conservative by design.

Neither extractor infers missing data; anything not stated is left unknown.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.schemas.patient import (
    Biomarker, Conflict, Demographics, Diagnosis, Fact, LabValue, Location, MedicalHistory, ParseResponse,
    PatientProfile, Preferences, Treatment, normalize_stage,
)
from app.services.llm import UNTRUSTED_DATA_POLICY, LLMClient, LLMError
from app.services.terminology import BIOMARKER_SYNONYMS, THERAPY_CLASSES, biomarker_pattern

# ---------------- Claude extraction schema -----------------------------------------------------------
# Deliberately flat with no nullable fields: one list of {field, value, evidence} facts with an enum field
# name. (A nested schema with ~20 optional objects exceeded the structured-output grammar size limit.)

FactField = Literal[
    "age_years", "sex", "city", "state", "postal_code", "country", "travel_radius_miles",
    "primary_condition", "subtype", "stage", "histology", "diagnosis_date", "metastatic",
    "ecog_performance_status", "prior_trial_participation", "pregnant_or_breastfeeding",
    "current_medication", "comorbidity", "finding", "treatment_interest", "willing_to_travel", "remote_ok",
]


class XFact(BaseModel):
    field: FactField
    value: str = Field(description="Value as text: numbers as digits, booleans as 'yes'/'no', sex as 'female'/'male', "
                                   "dates as YYYY-MM-DD or YYYY-MM")
    evidence: str = Field(description="Exact substring copied from the narrative that states this value")


class XBiomarker(BaseModel):
    name: str
    status: Literal["positive", "negative", "mutated", "wild_type", "amplified", "not_detected", "other"]
    detail: str = Field(description="e.g. 'exon 19 deletion', 'IHC 3+'; empty string if not stated")
    evidence: str


class XTreatment(BaseModel):
    name: str
    category: str = Field(description="e.g. chemotherapy, surgery, targeted therapy; empty string if unclear")
    status: Literal["completed", "ongoing", "planned", "unknown"]
    progression: Literal["yes", "no", "unknown"] = Field(
        description="'yes' only if the text explicitly says the disease progressed on/after this treatment")
    evidence: str


class XLab(BaseModel):
    name: str
    value: float
    unit: str
    evidence: str


class XConflict(BaseModel):
    field: str
    description: str


class ExtractedProfile(BaseModel):
    facts: list[XFact]
    biomarkers: list[XBiomarker]
    prior_treatments: list[XTreatment]
    labs: list[XLab]
    conflicts: list[XConflict]


PARSER_SYSTEM = f"""You extract a structured clinical profile from a patient's or caregiver's description, \
for the purpose of screening clinical trials.

Rules:
- Extract only what is explicitly stated. Do not infer, guess, or fill in typical values. Omit anything not \
stated: do not emit a fact for it.
- `facts` holds single values (one entry per field; current_medication, comorbidity, finding and \
treatment_interest may repeat). For every entry, copy the exact supporting phrase from the narrative into \
`evidence` (verbatim substring, same spelling). Entries without a verbatim quote will be discarded.
- Treatments the patient has NOT received (e.g. "haven't started immunotherapy") must not be listed as \
prior treatments. They may be a treatment_interest only if the person expresses interest.
- Set a treatment's progression to "yes" only if the text explicitly says the disease progressed, grew or \
came back on/after it. Otherwise "unknown". Medications currently being taken for other conditions are \
current_medication facts, not prior treatments.
- travel_radius_miles: convert kilometers to miles (1 km = 0.621 mi) and quote the original phrase.
- Use `conflicts` to list statements that contradict each other (e.g. two different ages).
- Use standard names for biomarkers (HER2, ER, PR, EGFR, ALK, KRAS, BRCA1, PD-L1, CFTR ...).

{UNTRUSTED_DATA_POLICY}"""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―−]", "-", s)
    return re.sub(r"\s+", " ", s).strip()


def evidence_in_text(evidence: str | None, text: str) -> bool:
    return bool(evidence) and len(evidence.strip()) >= 2 and _norm(evidence) in _norm(text)


def _numbers_in(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s or ""))


def _km_conversion_ok(miles: float, evidence: str) -> bool:
    if "km" not in evidence.lower() and "kilomet" not in evidence.lower():
        return False
    return any(abs(float(n) * 0.621371 - float(miles)) <= 2 for n in _numbers_in(evidence))


class _Verifier:
    """Drops model-extracted values that are not backed by a verbatim quote from the narrative."""

    def __init__(self, narrative: str):
        self.narrative = narrative
        self.dropped: list[str] = []

    def ok(self, label: str, evidence: str | None, numeric: float | int | None = None) -> bool:
        if not evidence_in_text(evidence, self.narrative):
            self.dropped.append(f"{label}: evidence quote not found in the description")
            return False
        if numeric is not None:
            num = f"{numeric:g}" if isinstance(numeric, float) else str(numeric)
            if num not in _numbers_in(evidence) and not _km_conversion_ok(numeric, evidence):
                self.dropped.append(f"{label}: value {num} does not appear in its evidence quote")
                return False
        return True


_INT_FIELDS = {"age_years": (0, 120), "travel_radius_miles": (1, 5000), "ecog_performance_status": (0, 5)}
_BOOL_FIELDS = {"metastatic", "prior_trial_participation", "pregnant_or_breastfeeding", "willing_to_travel", "remote_ok"}
_YES = {"yes", "true", "y"}
_NO = {"no", "false", "n"}


def _coerce(field: str, raw: str):
    """Typed value for a fact, or raises ValueError."""
    v = raw.strip()
    if field in _INT_FIELDS:
        n = round(float(re.sub(r"[^\d.]", "", v)))
        lo, hi = _INT_FIELDS[field]
        if not lo <= n <= hi:
            raise ValueError(f"outside {lo}–{hi}")
        return n
    if field in _BOOL_FIELDS:
        if v.lower() in _YES:
            return True
        if v.lower() in _NO:
            return False
        raise ValueError("not yes/no")
    if field == "sex":
        if v.lower() in ("female", "male"):
            return v.lower()
        raise ValueError("not female/male")
    if field == "diagnosis_date":
        d = date.fromisoformat(v if len(v) == 10 else v + "-01")
        if d > date.today():
            raise ValueError("in the future")
        return d
    if field == "stage":
        return v
    if not v:
        raise ValueError("empty")
    return v


def build_profile_from_extraction(x: ExtractedProfile, narrative: str) -> tuple[PatientProfile, list[str], list[str]]:
    v = _Verifier(narrative)
    warnings: list[str] = []
    single: dict[str, Fact] = {}
    multi: dict[str, list[Fact]] = {"current_medication": [], "comorbidity": [], "finding": [], "treatment_interest": []}
    loc_parts: dict[str, str] = {}
    loc_evidence: list[str] = []

    for f in x.facts:
        label = f.field.replace("_", " ")
        try:
            value = _coerce(f.field, f.value)
        except ValueError as exc:
            v.dropped.append(f"{label}: value '{f.value[:40]}' rejected ({exc})")
            continue
        if not v.ok(label, f.evidence, value if f.field in _INT_FIELDS and f.field != "ecog_performance_status" else None):
            continue
        if f.field == "ecog_performance_status" and str(value) not in _numbers_in(f.evidence):
            v.dropped.append(f"{label}: value {value} does not appear in its evidence quote")
            continue
        if f.field == "stage":
            m = re.search(r"\bstage\s+(iv|i{1,3}|0|[1-4])([abc]\d?)?\b", f.evidence, re.I)
            if m and normalize_stage(m.group(0)) != normalize_stage(str(value)):
                v.dropped.append(f"stage: value '{value}' does not match its quote '{m.group(0)}'")
                continue
        fact = Fact(value=value, source="model_extracted", evidence=f.evidence)
        if f.field in ("city", "state", "postal_code", "country"):
            loc_parts.setdefault(f.field, value)
            loc_evidence.append(f.evidence)
        elif f.field in multi:
            multi[f.field].append(fact)
        elif f.field in single and single[f.field].value != value:
            warnings.append(f"Two different values were extracted for {label}; please check it.")
        else:
            single.setdefault(f.field, fact)

    location = Location(**loc_parts, source="model_extracted" if loc_parts else "unknown",
                        evidence="; ".join(dict.fromkeys(loc_evidence)) or None)
    biomarkers = [Biomarker(name=b.name, status=b.status, detail=b.detail or None, source="model_extracted",
                            evidence=b.evidence)
                  for b in x.biomarkers if v.ok(f"biomarker {b.name}", b.evidence)]
    treatments = [Treatment(name=t.name, category=t.category or None, status=t.status, progression=t.progression,
                            source="model_extracted", evidence=t.evidence)
                  for t in x.prior_treatments if v.ok(f"treatment {t.name}", t.evidence)]
    labs = []
    for lab in x.labs:
        if v.ok(f"lab {lab.name}", lab.evidence, lab.value):
            try:
                labs.append(LabValue(name=lab.name, value=lab.value, unit=lab.unit, source="model_extracted",
                                     evidence=lab.evidence))
            except ValidationError as exc:
                warnings.append(f"Lab '{lab.name}' was not used: {exc.errors()[0]['msg']}")

    g = lambda k: single.get(k, Fact())  # noqa: E731
    willing, remote = g("willing_to_travel").value, g("remote_ok").value
    profile = PatientProfile(
        demographics=Demographics(age_years=g("age_years"), sex=g("sex"), location=location,
                                  travel_radius_miles=g("travel_radius_miles")),
        diagnosis=Diagnosis(
            primary_condition=g("primary_condition"), subtype=g("subtype"), stage=g("stage"), histology=g("histology"),
            diagnosis_date=g("diagnosis_date"), metastatic=g("metastatic"), biomarkers=biomarkers,
            findings=multi["finding"],
        ),
        history=MedicalHistory(
            prior_treatments=treatments, current_medications=multi["current_medication"],
            comorbidities=multi["comorbidity"], ecog_performance_status=g("ecog_performance_status"), labs=labs,
            prior_trial_participation=g("prior_trial_participation"),
            pregnant_or_breastfeeding=g("pregnant_or_breastfeeding"),
        ),
        preferences=Preferences(willing_to_travel=willing, remote_ok=remote,
                                treatment_interests=[str(f.value) for f in multi["treatment_interest"]][:10]),
        conflicts=[Conflict(field=c.field, description=c.description) for c in x.conflicts],
    )
    return profile, warnings, v.dropped


# ---------------- Deterministic fallback extractor ----------------

_NEGATION = re.compile(r"\b(?:not|never|no|haven't|hasn't|hadn't|didn't|don't|doesn't|without|yet to|declined|refused)\b"
                       r"|n't\b", re.I)
KNOWN_CONDITIONS = [
    "triple-negative breast cancer", "breast cancer", "non-small cell lung cancer", "small cell lung cancer",
    "lung cancer", "colorectal cancer", "prostate cancer", "pancreatic cancer", "ovarian cancer", "melanoma",
    "glioblastoma", "multiple myeloma", "acute myeloid leukemia", "lymphoma", "parkinson's disease",
    "parkinson disease", "alzheimer's disease", "multiple sclerosis", "amyotrophic lateral sclerosis",
    "type 2 diabetes", "type 1 diabetes", "heart failure", "coronary artery disease", "atrial fibrillation",
    "chronic kidney disease", "cystic fibrosis", "sickle cell disease", "huntington's disease",
    "duchenne muscular dystrophy", "spinal muscular atrophy", "fabry disease", "asthma", "copd",
    "rheumatoid arthritis", "lupus", "crohn's disease", "ulcerative colitis", "hepatocellular carcinoma",
]
_COND_RE = re.compile("|".join(re.escape(c) for c in sorted(KNOWN_CONDITIONS, key=len, reverse=True)), re.I)
_STATE_ABBR = r"(?:A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])"


def _sentences(text: str) -> list[tuple[int, str]]:
    out, pos = [], 0
    for s in re.split(r"(?<=[.!?;])\s+", text):
        idx = text.find(s, pos)
        out.append((idx, s))
        pos = idx + len(s)
    return out


def _negated(sentence: str, start: int) -> bool:
    window = sentence[max(0, start - 40):start]
    clause = re.split(r"[,;]| but | and ", window)[-1]
    return bool(_NEGATION.search(clause))


def rule_extract(narrative: str) -> PatientProfile:
    text = narrative
    rf = lambda value, ev: Fact(value=value, source="rule_extracted", evidence=ev)  # noqa: E731

    age = Fact()
    m = re.search(r"\b(\d{1,3})[- ]?(?:years?|yrs?|y/o|yo)[- ]?(?:old)?\b", text, re.I) or \
        re.search(r"\b(?:age|aged)\s*(\d{1,3})\b", text, re.I)
    if m and 0 <= int(m.group(1)) <= 120:
        age = rf(int(m.group(1)), m.group(0))

    sex = Fact()
    fm = re.search(r"\b(woman|female|girl|lady|mother)\b", text, re.I)
    ml = re.search(r"\b(man|male|boy|gentleman|father)\b", text, re.I)
    conflicts: list[Conflict] = []
    if fm and ml:
        conflicts.append(Conflict(field="sex", description=f"Both '{fm.group(0)}' and '{ml.group(0)}' are mentioned."))
    elif fm:
        sex = rf("female", fm.group(0))
    elif ml:
        sex = rf("male", ml.group(0))

    ages = {int(a) for a in re.findall(r"\b(\d{1,3})[- ]?(?:years?|yrs?)[- ]?old\b", text, re.I)}
    if len(ages) > 1:
        conflicts.append(Conflict(field="age", description=f"Different ages mentioned: {sorted(ages)}."))
        age = Fact()

    location = Location()
    lm = re.search(r"\b(?:living in|live in|lives in|located in|based in|from|reside in|near)\s+"
                   r"([A-Z][A-Za-z.' -]{1,40}?)(?:,\s*(" + _STATE_ABBR + r"|[A-Z][a-z]+(?: [A-Z][a-z]+)?))?(?=[.,;]|\s+(?:and|I|i'm|with)\b|$)",
                   text)
    if lm:
        location = Location(city=lm.group(1).strip(), state=(lm.group(2) or None), source="rule_extracted",
                            evidence=lm.group(0))
    radius = Fact()
    rm = re.search(r"\b(?:within|up to|travel(?:\s+up\s+to)?)\s+(\d{1,4})\s*(miles?|mi|km|kilometers?)\b", text, re.I)
    if rm:
        val = int(rm.group(1))
        if rm.group(2).lower().startswith("k"):
            val = round(val * 0.621371)
        radius = rf(val, rm.group(0))

    condition = Fact()
    cm = _COND_RE.search(text)
    if cm:
        condition = rf(cm.group(0).lower(), cm.group(0))

    stage = Fact()
    sm = re.search(r"\bstage\s+(0|iv|i{1,3}|[1-4])([abc]\d?)?\b", text, re.I)
    if sm:
        stage = rf(sm.group(0), sm.group(0))
    metastatic = Fact()
    mm = re.search(r"\bmetasta(?:tic|sis|sized|ses)\b", text, re.I)
    if mm:
        sent = next((s for i, s in _sentences(text) if i <= mm.start() < i + len(s)), text)
        if not _negated(sent, sent.lower().find(mm.group(0).lower())):
            metastatic = rf(True, mm.group(0))

    biomarkers: list[Biomarker] = []
    status_words = {
        "positive": "positive", "+": "positive", "pos": "positive", "negative": "negative", "-": "negative",
        "neg": "negative", "mutation": "mutated", "mutated": "mutated", "mutant": "mutated", "amplified": "amplified",
        "amplification": "amplified", "wild-type": "wild_type", "wild type": "wild_type", "wildtype": "wild_type",
        "deletion": "mutated", "fusion": "mutated", "rearrangement": "mutated", "insertion": "mutated",
    }
    for canon in BIOMARKER_SYNONYMS:
        if canon in ("HbA1c",):
            continue
        pat = re.compile(biomarker_pattern(canon) + r"(?:[\s-]*(?:exon\s*\d+\s*)?)"
                         r"(positive|negative|pos|neg|\+|-|mutation|mutated|mutant|amplified|amplification|"
                         r"wild[- ]?type|deletion|fusion|rearrangement|insertion)", re.I)
        for bm in pat.finditer(text):
            st = status_words[bm.group(1).lower()]
            if any(b.name == canon for b in biomarkers):
                if any(b.name == canon and b.status != st for b in biomarkers):
                    conflicts.append(Conflict(field=f"biomarker {canon}", description="Reported with different statuses."))
                continue
            detail = None
            ex = re.search(r"exon\s*\d+\s*\w*", bm.group(0), re.I)
            if ex:
                detail = ex.group(0)
            biomarkers.append(Biomarker(name=canon, status=st, detail=detail, source="rule_extracted",
                                        evidence=bm.group(0)))

    treatments: list[Treatment] = []
    generic = {"surgery": "surgery", "mastectomy": "surgery", "lumpectomy": "surgery", "chemotherapy": "chemotherapy",
               "chemo": "chemotherapy", "radiation": "radiation", "radiotherapy": "radiation"}
    drug_terms = {m: cls for cls, members in THERAPY_CLASSES.items() for m in members if len(m) > 4}
    for idx, sent in _sentences(text):
        for term, cat in list(generic.items()) + list(drug_terms.items()):
            for tm in re.finditer(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", sent, re.I):
                if _negated(sent, tm.start()):
                    continue
                name = tm.group(0).lower()
                if any(t.name == name for t in treatments):
                    continue
                if re.search(r"\b(interested in|want to try|considering|looking for)\b", sent[:tm.start()], re.I):
                    continue
                completed = bool(re.search(r"\b(completed|finished|had|underwent|received|after|treated with|previously)\b",
                                           sent, re.I))
                ongoing = bool(re.search(r"\b(currently|ongoing|on)\b\s+(?:\w+\s+){0,2}" + re.escape(term), sent, re.I))
                progressed = re.search(r"\bprogress(?:ed|ion)\b[^.]{0,40}" + re.escape(term) + r"|"
                                       + re.escape(term) + r"[^.]{0,40}\bprogress(?:ed|ion)\b", sent, re.I)
                treatments.append(Treatment(
                    name=name, category=cat, status="ongoing" if ongoing else "completed" if completed else "unknown",
                    progression="yes" if progressed and not _negated(sent, progressed.start()) else "unknown",
                    source="rule_extracted", evidence=sent.strip()[:400],
                ))

    interests = [m.group(1).strip() for m in re.finditer(r"interested in ([a-z -]{3,40}?)(?: trials?| studies| options)?[.,]",
                                                         text, re.I) if "clinical trial" not in m.group(1).lower()]

    ecog = Fact()
    em = re.search(r"\bECOG(?:[\s-]+(?:PS|performance status|score|status))?\s*(?:of|is|=|:)?\s*([0-5])\b", text, re.I)
    if em:
        ecog = rf(int(em.group(1)), em.group(0))

    return PatientProfile(
        demographics=Demographics(age_years=age, sex=sex, location=location, travel_radius_miles=radius),
        diagnosis=Diagnosis(primary_condition=condition, stage=stage, metastatic=metastatic, biomarkers=biomarkers),
        history=MedicalHistory(prior_treatments=treatments, ecog_performance_status=ecog),
        preferences=Preferences(treatment_interests=interests[:5]),
        conflicts=conflicts,
    )


async def parse_narrative(narrative: str, llm: LLMClient) -> ParseResponse:
    narrative = narrative.strip()
    try:
        extracted = await llm.structured(
            system=PARSER_SYSTEM,
            user=f"<patient_narrative>\n{narrative}\n</patient_narrative>\n\nExtract the structured profile.",
            output=ExtractedProfile, max_tokens=6000,
        )
        profile, warnings, dropped = build_profile_from_extraction(extracted, narrative)
        return ParseResponse(profile=profile, extraction_method="claude", warnings=warnings, dropped_unverified=dropped)
    except LLMError as exc:
        profile = rule_extract(narrative)
        return ParseResponse(
            profile=profile, extraction_method="rules",
            warnings=[f"AI extraction unavailable ({exc}). A conservative rule-based extractor was used; "
                      "please review and complete the profile."],
        )
