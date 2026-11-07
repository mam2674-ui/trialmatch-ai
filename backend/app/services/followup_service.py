"""Smart follow-up questions.

Questions are generated only from information gaps that actually block an assessment in the current
results, and are prioritized by how many studies they could move (e.g. from "Needs more information"
to a clearer category). Each question carries a `patch` describing exactly how an answer updates the
structured profile; answers are always recorded as patient_provided.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from app.schemas.match import FollowUpQuestion, MatchResult
from app.schemas.patient import Biomarker, Fact, PatientProfile
from app.services import evidence_validator as ev

_BIOMARKER_Q = re.compile(r"\b(HER2|EGFR|ALK|ROS1|KRAS|BRAF|BRCA1|BRCA2|PD-L1|PIK3CA|ESR1|ER|PR|MSI-H|LRRK2|GBA|CFTR)\b")


def _qid(text: str) -> str:
    return hashlib.sha1(text.lower().encode()).hexdigest()[:10]


_Q_STOP = set("""a an the and or of to in on for is it if so any have has had you your been was were be did do does
are told this that from with about cancer disease patient there other""".split())


def _similar(a: str, b: str) -> bool:
    """Questions about the same topic ("spread to the brain ...") are merged even when worded differently."""
    ta = {w for w in ev.norm(a).split() if w not in _Q_STOP and len(w) > 2}
    tb = {w for w in ev.norm(b).split() if w not in _Q_STOP and len(w) > 2}
    if ta & tb & _TOPICS:
        return True
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


# Specific clinical topics: two questions that both name one are about the same thing.
_TOPICS = {"brain", "cns", "leptomeningeal", "spine", "spinal", "pneumonitis", "ild", "interstitial", "hepatitis",
           "hiv", "pregnant", "pregnancy", "breastfeeding", "transplant", "seizures", "dementia"}


_YES_NO_START = re.compile(r"^(is|are|was|were|do|does|did|has|have|had|can|could|will|would|should|besides|apart)\b", re.I)


def generate_questions(p: PatientProfile, results: list[MatchResult], limit: int = 6) -> list[FollowUpQuestion]:
    buckets: dict[str, dict] = {}
    weight = {"NEEDS_MORE_INFORMATION": 2.0, "POTENTIAL_MATCH": 1.5, "REQUIRES_CLINICAL_REVIEW": 1.0,
              "POTENTIALLY_INELIGIBLE": 0.0}

    def add(key: str, question: str, why: str, patch: dict, nct: str, w: float) -> None:
        b = buckets.setdefault(key, {"question": question, "why": why, "patch": patch, "trials": set(), "score": 0.0})
        if nct not in b["trials"]:
            b["trials"].add(nct)
            b["score"] += w

    known_markers = {b.name for b in p.diagnosis.biomarkers}
    for r in results:
        w = weight[r.eligibility.category]
        if w == 0:
            continue
        for c in r.criteria:
            if c.assessment != "UNKNOWN" or not c.needs_info:
                continue
            if c.criterion_id == "AGE":
                add("age", "How old is the patient?", "Several studies have age limits.",
                    {"type": "set_field", "path": "demographics.age_years", "input": "number"}, r.trial.nct_id, w)
                continue
            if c.criterion_id == "SEX":
                add("sex", "Which sex should be used for study eligibility?", "Some studies enroll only one sex.",
                    {"type": "set_field", "path": "demographics.sex", "input": "choice", "choices": ["female", "male"]},
                    r.trial.nct_id, w)
                continue
            if c.impact != "high":
                continue
            m = _BIOMARKER_Q.search(c.criterion_text)
            if m and m.group(1) not in known_markers:
                marker = m.group(1)
                add(f"biomarker:{marker}", f"Do you know whether the tumor or genetic testing was positive for {marker}?",
                    f"{marker} status is a stated requirement for some studies.",
                    {"type": "set_biomarker", "name": marker, "yes": "positive", "no": "negative"}, r.trial.nct_id, w)
                continue
            prog = re.search(r"\bprogress(?:ed|ion)\b", c.criterion_text, re.I)
            treated = [t for t in p.history.prior_treatments if t.progression == "unknown"
                       and t.category not in ("surgery", "radiation")]
            if prog and treated:
                t = treated[0]
                add(f"progression:{t.name.lower()}", f"Did the disease grow or progress during or after {t.name}?",
                    "Some studies require documented progression after a previous therapy.",
                    {"type": "set_progression", "treatment": t.name}, r.trial.nct_id, w)
                continue
            # Only questions a Yes / No / Not sure answer can settle ("..., or ...?" either/or questions stay on the
            # study's own criterion list instead).
            if c.question and _YES_NO_START.match(c.question.strip()) and not re.search(r",\s*or\b", c.question):
                existing = next((k for k, b in buckets.items() if k.startswith("free:") and _similar(b["question"], c.question)), None)
                key = existing or f"free:{_qid(c.question)}"
                add(key, c.question, f"Needed to check criterion {c.criterion_id} of {r.trial.nct_id}.",
                    {"type": "add_finding", "question": c.question}, r.trial.nct_id, w)

    qs = [FollowUpQuestion(id=_qid(k), question=b["question"], why=b["why"], patch=b["patch"],
                           affected_trials=sorted(b["trials"]), priority=round(b["score"], 2))
          for k, b in buckets.items()]
    for q in qs:
        if q.patch["type"] == "set_field":
            q.options = []
    qs.sort(key=lambda q: -q.priority)
    return qs[:limit]


def apply_answer(p: PatientProfile, q: FollowUpQuestion, answer: str, value: str | int | None = None) -> PatientProfile:
    """Return a new profile with the answer applied. 'not_sure' records nothing (stays unknown)."""
    prof = p.model_copy(deep=True)
    patch = q.patch
    if answer == "not_sure" and patch["type"] != "set_field":
        return prof
    kind = patch["type"]
    if kind == "set_biomarker":
        status = patch["yes"] if answer == "yes" else patch["no"]
        prof.diagnosis.biomarkers = [b for b in prof.diagnosis.biomarkers if b.name != patch["name"]]
        prof.diagnosis.biomarkers.append(Biomarker(name=patch["name"], status=status, source="patient_provided",
                                                   evidence=f"Answered '{answer}' to: {q.question}"))
    elif kind == "set_progression":
        for t in prof.history.prior_treatments:
            if t.name == patch["treatment"]:
                t.progression = "yes" if answer == "yes" else "no"
                t.source = "patient_provided"
    elif kind == "add_finding":
        prof.diagnosis.findings.append(Fact[str](value=f"{q.question} — patient answered: {answer}",
                                                 source="patient_provided"))
    elif kind == "set_field" and value is not None:
        section, field = patch["path"].split(".")
        target = getattr(prof, section)
        setattr(target, field, Fact(value=value, source="patient_provided"))
    return prof
