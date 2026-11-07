"""Deterministic eligibility checks for clear-cut, objective requirements.

Design principles
  * Unknown patient data is never evidence of eligibility: it yields UNKNOWN, never MET.
  * A rule may only return a *definitive* NOT_MET (inclusion) or MET (exclusion) when the criterion is
    unambiguous: no alternatives ("or"), no exceptions ("unless", "except", "allowed"), and no time
    windows we cannot evaluate ("within 4 weeks").
  * A rule returns MET for an inclusion criterion only when the criterion is short and single-topic,
    because one satisfied sub-requirement does not satisfy a multi-part criterion.
  * Every result cites the exact patient fact and criterion text used.
Definitive rule results take precedence over model output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.match import CriterionResult
from app.schemas.patient import PatientProfile, Treatment, stage_number
from app.schemas.trial import Criterion, NormalizedTrial
from app.services.terminology import (
    BIOMARKER_SYNONYMS, THERAPY_CLASSES, biomarker_pattern, normalize_biomarker_name, therapy_classes_for,
)

RECRUITING = {"RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}
_EXCEPTION = re.compile(r"\b(unless|except|allowed|permitted|acceptable|eligible if|may be enrolled|exception|"
                        r"provided that|as long as|regardless)\b", re.I)
_TIME_WINDOW = re.compile(r"\b(within|in the (?:last|past|previous)|prior to (?:the )?(?:first|start|enrol|random|day)|"
                          r"before (?:the )?(?:first|start|enrol|random|day)|\d+\s*(?:days?|weeks?|months?|years?))\b", re.I)
_OR = re.compile(r"\b(or|and/or)\b|/", re.I)
POS = {"positive", "mutated", "amplified"}
NEG = {"negative", "wild_type", "not_detected"}


@dataclass
class RuleOutcome:
    result: CriterionResult
    definitive: bool


def _blocker(kind: str, assessment: str) -> bool:
    return (kind in ("inclusion", "structured", "unclassified") and assessment == "NOT_MET") or (
        kind == "exclusion" and assessment == "MET")


def _res(c_id: str, kind: str, text: str, assessment: str, explanation: str, patient_ev: list[str],
         trial_ev: str | None, *, needs_info=False, question=None, impact="high") -> CriterionResult:
    return CriterionResult(
        criterion_id=c_id, kind=kind, criterion_text=text, assessment=assessment,
        is_blocker=_blocker(kind, assessment), patient_evidence=patient_ev, trial_evidence=trial_ev,
        explanation=explanation, needs_info=needs_info,
        unknown_reason="missing_patient_info" if assessment == "UNKNOWN" and needs_info else None,
        impact=impact, question=question, source="rule",
    )


# ---------------- structured fields ----------------

def structured_checks(p: PatientProfile, t: NormalizedTrial) -> list[CriterionResult]:
    out: list[CriterionResult] = []
    age = p.demographics.age_years.value
    lo, hi = t.min_age_years, t.max_age_years
    age_text = f"Minimum age: {t.minimum_age or 'not specified'}; maximum age: {t.maximum_age or 'not specified'}"
    if lo is None and hi is None:
        out.append(_res("AGE", "structured", age_text, "NOT_APPLICABLE", "The study lists no age limits.", [], None,
                        impact="routine"))
    elif age is None:
        out.append(_res("AGE", "structured", age_text, "UNKNOWN", "Your age was not provided, so the study's age "
                        "limits could not be checked.", [], age_text, needs_info=True,
                        question="How old is the patient?"))
    else:
        ok = (lo is None or age >= lo) and (hi is None or age <= hi)
        out.append(_res("AGE", "structured", age_text, "MET" if ok else "NOT_MET",
                        f"Age {age} is {'within' if ok else 'outside'} the study's listed age range.",
                        [f"Age {age}"], age_text))

    sex = p.demographics.sex.value
    if t.sex in (None, "ALL"):
        out.append(_res("SEX", "structured", f"Sex: {t.sex or 'not specified'}", "NOT_APPLICABLE",
                        "The study accepts all sexes.", [], None, impact="routine"))
    elif sex is None:
        out.append(_res("SEX", "structured", f"Sex: {t.sex}", "UNKNOWN",
                        f"This study enrolls {t.sex.lower()} participants only; sex was not provided.", [],
                        f"Sex: {t.sex}", needs_info=True, question="What sex is relevant for study eligibility (female or male)?"))
    else:
        ok = t.sex.lower() == sex
        out.append(_res("SEX", "structured", f"Sex: {t.sex}", "MET" if ok else "NOT_MET",
                        f"The study enrolls {t.sex.lower()} participants; the profile lists {sex}.",
                        [f"Sex {sex}"], f"Sex: {t.sex}"))

    status = t.overall_status or "UNKNOWN"
    ok = status in RECRUITING
    out.append(_res("STATUS", "structured", f"Overall recruitment status: {status}",
                    "MET" if ok else "NOT_MET",
                    "The study is listed as open or about to open for enrollment." if ok else
                    f"The study is listed as {status.replace('_', ' ').lower()}, so it is not currently enrolling.",
                    [], f"Overall recruitment status: {status}", impact="high" if not ok else "routine"))
    return out


# ---------------- criterion-text rules ----------------

def _single_topic(text: str) -> bool:
    return len(text) <= 110 and text.count(".") <= 1 and "\n" not in text


def _clause_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind(";", 0, start), text.rfind("\n", 0, start)) + 1
    rights = [i for i in (text.find(".", end), text.find(";", end), text.find("\n", end)) if i != -1]
    right = min(rights) if rights else len(text)
    return text[left:right]


# Criteria that apply only to a subgroup ("If ...", "COHORT A: ...", "Patients with X must ...") cannot
# produce definitive results, because we cannot tell whether the patient belongs to that subgroup.
_CONDITIONAL = re.compile(
    r"^\s*(?:if|for|in|when|where|unless)\b"
    r"|^\s*(?:patients?|participants?|subjects?|women|men|those|individuals)\s+(?:with|who|whose)\b[^.]*?"
    r"\b(?:must|should|will|are required|need)\b"
    r"|^\s*(?:part|cohort|arm|group|sub-?study|module|expansion|escalation|dose)\b[^:]{0,40}:"
    r"|^[^.]{0,80}\b(?:cohorts?|arms?|parts?|sub-?studies)\s+[A-Z0-9][\w,]*", re.I)
_CONDITIONAL_CAPS = re.compile(r"^\s*[A-Z0-9 ,/\-]{0,40}\b(?:COHORT|PART|ARM|GROUP|ESCALATION|EXPANSION)\b[^:]{0,30}:")


def _conditional(text: str) -> bool:
    return bool(_CONDITIONAL.search(text) or _CONDITIONAL_CAPS.search(text))


def _top_line(text: str) -> str:
    """The criterion's own statement, excluding nested sub-items (which are often definitions or alternatives)."""
    return text.split("\n", 1)[0]


_STATUS_IN_CRIT = [
    (re.compile(r"^[\s-]*(?:\(?\s*)?(positive|\+|pos\b|overexpress|amplif)", re.I), "pos"),
    (re.compile(r"^[\s-]*(?:\(?\s*)?(negative|-(?!\w)|neg\b|non-amplified|wild[- ]?type|low\b|ultralow)", re.I), "neg"),
    (re.compile(r"^[\s-]*(?:gene\s+)?(?:activating\s+|sensitizing\s+)?(mutation|mutated|mutant|alteration|deletion|"
                r"rearrange|fusion|exon)", re.I), "pos"),
]
_PRE_STATUS = re.compile(r"(activating|sensitizing|documented|confirmed)\s+(?:\w+\s+){0,2}$", re.I)


def _criterion_biomarker_requirements(text: str) -> list[tuple[str, str, str, str, int]]:
    """Return (marker, 'pos'|'neg'|'low', clause, preceding words, position) for biomarker statuses in a criterion."""
    found = []
    for m in re.finditer(r"\b(triple[- ]negative|TNBC)\b", text, re.I):
        clause = _clause_around(text, m.start(), m.end())
        for canon in ("HER2", "ER", "PR"):
            found.append((canon, "neg", clause, text[max(0, m.start() - 30): m.start()], m.start()))
    for canon in BIOMARKER_SYNONYMS:
        if canon == "HbA1c":
            continue
        for m in re.finditer(biomarker_pattern(canon), text, re.I):
            # Case-sensitive guard for short ambiguous markers (ER, PR, MET, RET): must be uppercase in source.
            if canon in ("ER", "PR", "MET", "RET") and m.group(0) != m.group(0).upper():
                continue
            tail = text[m.end(): m.end() + 30]
            if canon == "HER2" and re.match(r"^[\s-]*(low|ultralow|0\b|1\+|2\+)", tail, re.I):
                found.append((canon, "low", _clause_around(text, m.start(), m.end()), "", m.start()))
                continue
            status = None
            for rx, s in _STATUS_IN_CRIT:
                if rx.match(tail):
                    status = s
                    break
            if status is None and _PRE_STATUS.search(text[max(0, m.start() - 40): m.start()]):
                status = "pos"
            if status:
                found.append((canon, status, _clause_around(text, m.start(), m.end()),
                              text[max(0, m.start() - 30): m.start()], m.start()))
    return found


# Specific variants (exon numbers, protein changes such as L858R / G12C / V600E, F508del).
_VARIANT = re.compile(r"(?i:\bexon\s*\d+\b)|\b[A-Z]\d{2,4}[A-Z]\b|\bF508del\b|\bdel19\b")


def _variant_compatible(clause: str, detail: str | None) -> bool:
    """A criterion naming specific variants (e.g. 'exon 20 insertion') is only decidable when the patient's
    variant is known and is one of those named; otherwise the rule must not decide."""
    variants = [v.lower().replace(" ", "") for v in _VARIANT.findall(clause)]
    if not variants:
        return True
    d = (detail or "").lower().replace(" ", "")
    return bool(d) and any(v in d for v in variants)


# Words that carry no extra requirement in a biomarker criterion. Anything else left over means the criterion
# asks for more than the biomarker (treatment history, stage, sex ...), so a rule must not call it MET.
_FILLER = set("""a an the of with and in for to be is are must have has had patients patient participants participant
subjects subject histologically cytologically pathologically confirmed documented known diagnosis diagnosed disease
cancer tumor tumour carcinoma breast lung nsclc non-small cell positive negative mutation mutations mutated mutant
activating sensitizing status expression expressing overexpression amplified amplification gene alteration test
tested result results by ihc ish fish ngs or as per defined local central laboratory assay""".split())


def _only_biomarker_requirement(text: str) -> bool:
    bare = re.sub(r"\([^)]*\)", " ", text.lower())
    tokens = [w for w in re.findall(r"[a-z][a-z0-9+\-]*", bare)]
    residual = []
    for w in tokens:
        parts = [x for x in re.split(r"[-+]", w) if x]
        if w in _FILLER or all(x in _FILLER or normalize_biomarker_name(x) in BIOMARKER_SYNONYMS for x in parts):
            continue
        if normalize_biomarker_name(w) in BIOMARKER_SYNONYMS:
            continue
        residual.append(w)
    return not residual


def biomarker_rules(p: PatientProfile, c: Criterion) -> RuleOutcome | None:
    reqs = _criterion_biomarker_requirements(c.text)
    if not reqs or _conditional(c.text):
        return None
    pmarkers = {b.name: b for b in p.diagnosis.biomarkers}
    top_len = len(_top_line(c.text))
    for canon, req, clause, pre, pos in reqs:
        b = pmarkers.get(canon)
        if b is None or req == "low" or b.status == "other" or pos >= top_len:
            continue
        pstat = "pos" if b.status in POS else "neg" if b.status in NEG else None
        if pstat is None:
            continue
        if pstat == "pos" and not _variant_compatible(clause, b.detail):
            continue
        # "or" inside parentheses usually lists test methods ("IHC 3+ or ISH+"), not alternative populations.
        bare = re.sub(r"\([^)]*\)", "", clause)
        ambiguous = bool(_OR.search(bare)) or bool(_EXCEPTION.search(clause))
        negated = bool(re.search(r"\b(no|not|without|absence of|lack of|negative for)\b[^,;.]*$", pre, re.I))
        if negated:
            req = "neg" if req == "pos" else "pos"
        match = pstat == req
        ev = [f"{b.name} {b.status.replace('_', ' ')}{' (' + b.detail + ')' if b.detail else ''}"]
        if c.kind in ("inclusion", "unclassified"):
            if not match and not ambiguous:
                return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "NOT_MET",
                                        f"The study requires {canon}-{'positive/altered' if req == 'pos' else 'negative'} "
                                        f"disease here, but the profile reports {canon} {b.status.replace('_', ' ')}.",
                                        ev, clause.strip()), True)
            if match and _only_biomarker_requirement(c.text) and not ambiguous:
                return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "MET",
                                        f"The profile reports {canon} {b.status.replace('_', ' ')}, consistent with this requirement.",
                                        ev, clause.strip()), True)
        elif c.kind == "exclusion" and not ambiguous:
            if match:
                return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "MET",
                                        f"This exclusion applies to {canon}-{'positive/altered' if req == 'pos' else 'negative'} "
                                        f"disease, and the profile reports {canon} {b.status.replace('_', ' ')}.",
                                        ev, clause.strip()), True)
            if _single_topic(c.text):
                return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "NOT_MET",
                                        f"This exclusion applies to {canon}-{'positive/altered' if req == 'pos' else 'negative'} "
                                        f"disease; the profile reports {canon} {b.status.replace('_', ' ')}, so it does not apply.",
                                        ev, clause.strip()), True)
    return None


_PRIOR = re.compile(r"\b(prior|previous|previously|received|treated with|treatment with|therapy with|exposure to|"
                    r"history of|naive|naïve)\b", re.I)
_NO_PRIOR = re.compile(r"\b(no prior|no previous|not (?:have )?(?:been )?(?:previously )?(?:received|treated)|"
                       r"naive|naïve|must not have received|without prior|untreated)\b", re.I)


def _patient_therapy_hits(p: PatientProfile, text: str) -> list[tuple[str, str]]:
    """(patient treatment name, matched term in criterion) when the criterion names the drug or its class."""
    low = text.lower()
    hits = []
    for tr in p.history.prior_treatments:
        if tr.status not in ("completed", "ongoing", "unknown"):
            continue
        name = tr.name.lower()
        if len(name) > 3 and re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low):
            hits.append((tr.name, tr.name))
            continue
        for cls in therapy_classes_for(name):
            terms = [cls.lower()] + [m for m in THERAPY_CLASSES[cls] if len(m) > 5]
            for term in terms:
                if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low):
                    hits.append((tr.name, term))
                    break
    return hits


GENERIC_TREATMENTS = {"surgery", "chemotherapy", "chemo", "radiation", "radiotherapy", "mastectomy", "lumpectomy",
                      "immunotherapy", "hormone therapy", "endocrine therapy", "targeted therapy"}


def prior_therapy_rules(p: PatientProfile, c: Criterion) -> RuleOutcome | None:
    """Only specific drugs or drug classes. Generic categories ("chemotherapy", "surgery") are too coarse:
    "adjuvant chemotherapy" or "major surgery within 4 weeks" cannot be decided from "had chemotherapy"."""
    if not (p.history.prior_treatments or p.history.current_medications) or _conditional(c.text):
        return None
    top = _top_line(c.text)
    if not _PRIOR.search(top):
        return None
    specific = p.model_copy(deep=True)
    specific.history.prior_treatments = [t for t in p.history.prior_treatments
                                         if t.name.lower() not in GENERIC_TREATMENTS and t.category != "surgery"]
    # Current medications are exposures too ("Current treatment with an SGLT2 inhibitor").
    specific.history.prior_treatments += [Treatment(name=str(m.value), status="ongoing", source=m.source)
                                          for m in p.history.current_medications if m.value]
    hits = _patient_therapy_hits(specific, top)
    # The drug must be the object of the prior-treatment phrase, not merely mentioned elsewhere in the criterion.
    hits = [(d, t) for d, t in hits
            if _PRIOR.search(top[max(0, top.lower().find(t.lower()) - 80): max(top.lower().find(t.lower()), 0)])]
    if not hits:
        return None
    drug, term = hits[0]
    clause = _clause_around(top, max(top.lower().find(term.lower()), 0),
                            max(top.lower().find(term.lower()), 0) + len(term))
    unclear = bool(_EXCEPTION.search(clause)) or bool(_TIME_WINDOW.search(clause))
    ev = [f"Prior treatment: {drug}"]
    if c.kind == "exclusion":
        if unclear:
            return None  # time windows / exceptions need dates we do not have -> leave to model / review
        if re.search(r"\b(progress|refractory|resistan|intoleran)\w*", clause, re.I):
            return None  # exclusion depends on response to the drug, not mere exposure
        return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "MET",
                                f"This exclusion covers prior treatment with {term}, and the profile lists {drug}.",
                                ev, clause.strip()), True)
    if _NO_PRIOR.search(clause) and not unclear:
        return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "NOT_MET",
                                f"This requirement calls for no prior {term}, but the profile lists {drug}.",
                                ev, clause.strip()), True)
    return None


_STAGE_SPAN = re.compile(
    r"\bstages?\s+((?:0|iv|i{1,3}|[1-4])[abc]?\d?(?:\s*(?:,\s*(?:or|and)|-|–|to|through|or|and|/|,)\s*(?:stage\s+)?(?:0|iv|i{1,3}|[1-4])[abc]?\d?\b)*)",
    re.I)
_ROMAN = {"0": 0, "i": 1, "ii": 2, "iii": 3, "iv": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def _allowed_stages(text: str) -> tuple[set[int], str] | None:
    m = _STAGE_SPAN.search(text)
    if not m:
        return None
    tokens = re.findall(r"\b(iv|i{1,3}|0|[1-4])[abc]?\d?\b|(-|–|\bto\b|\bthrough\b)", m.group(1), re.I)
    stages: set[int] = set()
    prev, range_next = None, False
    for tok, sep in tokens:
        if sep:
            range_next = True
            continue
        n = _ROMAN[tok.lower()]
        if range_next and prev is not None:
            stages.update(range(prev, n + 1))
        stages.add(n)
        prev, range_next = n, False
    return stages, m.group(0)


def stage_rules(p: PatientProfile, c: Criterion) -> RuleOutcome | None:
    pstage = stage_number(p.diagnosis.stage.value)
    metastatic = p.diagnosis.metastatic.value
    if pstage is None and metastatic is None:
        return None
    if metastatic is None and pstage is not None:
        metastatic = pstage == 4  # AJCC: stage IV denotes distant metastasis for solid tumors
    text = c.text
    if re.search(r"\b(recurren|relaps)\w*", text, re.I):
        return None
    ev = [p.diagnosis.stage.value or ("metastatic disease" if metastatic else "non-metastatic disease")]
    span = _allowed_stages(_top_line(text)) if not _conditional(text) else None
    if pstage is None and metastatic is True:
        pstage = 4
    if span and pstage is not None and c.kind in ("inclusion", "unclassified"):
        allowed, quote = span
        clause = _clause_around(text, text.find(quote), text.find(quote) + len(quote))
        if pstage not in allowed and not re.search(r"\b(metastatic|advanced)\b", clause, re.I):
            return RuleOutcome(_res(c.criterion_id, c.kind, text, "NOT_MET",
                                    f"The study requires {quote}, but the profile reports "
                                    f"{p.diagnosis.stage.value or 'metastatic (stage IV) disease'}.",
                                    ev, quote), True)
    if c.kind in ("inclusion", "unclassified") and not _conditional(text):
        top = _top_line(text)
        m = re.search(r"\b(non-?metastatic|early[- ]stage|metastatic|stage iv)\b(?!\s+(?:setting|lesions?|site))", top, re.I)
        if m:
            clause = _clause_around(top, m.start(), m.end())
            pre = top[max(0, m.start() - 40): m.start()]
            negated = bool(re.search(r"\b(not|no|without|free of)\b[^,;.]*$", pre, re.I))
            wants_metastatic = m.group(1).lower() in ("metastatic", "stage iv") and not negated
            ambiguous = bool(re.search(r"\b(locally advanced|unresectable|advanced|recurrent|or|and/or)\b", clause, re.I))
            if wants_metastatic != metastatic and not ambiguous:
                need = "metastatic disease" if wants_metastatic else "non-metastatic disease"
                have = p.diagnosis.stage.value or ("metastatic disease" if metastatic else "non-metastatic disease")
                return RuleOutcome(_res(c.criterion_id, c.kind, text, "NOT_MET",
                                        f"The study requires {need} here, but the profile describes {have}.",
                                        ev, clause.strip()), True)
            if wants_metastatic == metastatic and _single_topic(text) and not ambiguous:
                return RuleOutcome(_res(c.criterion_id, c.kind, text, "MET",
                                        f"The profile describes {'metastatic' if metastatic else 'non-metastatic'} disease, "
                                        "consistent with this requirement.", ev, clause.strip()), True)
    if c.kind == "exclusion" and metastatic is True and not _conditional(text):
        m = re.search(r"\b(distant metasta\w*|metastatic disease|stage iv)\b", text, re.I)
        if m and _single_topic(text) and not _EXCEPTION.search(text) and not re.search(r"\b(brain|cns|leptomening)", text, re.I):
            return RuleOutcome(_res(c.criterion_id, c.kind, text, "MET",
                                    "This exclusion applies to metastatic disease, which the profile reports.",
                                    ev, m.group(0)), True)
    return None


_ECOG_ANCHOR = re.compile(r"\b(?:ECOG|Eastern Cooperative Oncology Group|WHO)\b", re.I)


def parse_ecog_range(text: str) -> tuple[int, int, str] | None:
    """Allowed ECOG range from phrasings like 'ECOG 0-1', 'of 0 to 1', '0, 1, or 2', '<= 1', 'less than or equal to (<=) 1'."""
    m = _ECOG_ANCHOR.search(text)
    if not m:
        return None
    window = re.split(r"[.;\n]|\b(?:KPS|Karnofsky|Lansky|life expectancy|and a|with no)\b", text[m.end(): m.end() + 90], maxsplit=1, flags=re.I)[0]
    lte = re.search(r"(≤|<=|<|less than or equal to|less than|no (?:greater|higher|more) than|at most|maximum of)\D{0,12}?([0-5])\b", window, re.I)
    if lte:
        hi = int(lte.group(2)) - (1 if lte.group(1) in ("<", "less than") else 0)
        more = re.match(r"\s*(?:,|or|and|,\s*or)\s*([0-5])\b", window[lte.end():], re.I)  # "<= 0 or 1"
        if more:
            hi = max(hi, int(more.group(1)))
        return 0, hi, text[m.start(): m.end() + lte.end()].strip()
    rng = re.search(r"\b([0-5])\s*(?:-|–|to|through)\s*([0-5])\b", window)
    if rng:
        return int(rng.group(1)), int(rng.group(2)), text[m.start(): m.end() + rng.end()].strip()
    nums = re.findall(r"(?<![\d.])([0-5])(?![\d.%])", window)
    if nums:
        vals = sorted({int(n) for n in nums})
        return vals[0], vals[-1], text[m.start(): m.end() + len(window)].strip()
    return None


def ecog_rules(p: PatientProfile, c: Criterion) -> RuleOutcome | None:
    ecog = p.history.ecog_performance_status.value
    if ecog is None or c.kind not in ("inclusion", "unclassified") or _conditional(c.text):
        return None
    parsed = parse_ecog_range(_top_line(c.text))
    if not parsed:
        return None
    lo, hi, quote = parsed
    has_alternative = bool(re.search(r"\b(karnofsky|kps|lansky)\b", c.text, re.I)) and bool(_OR.search(c.text))
    ev = [f"ECOG {ecog}"]
    if not lo <= ecog <= hi and not has_alternative:
        return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "NOT_MET",
                                f"The study requires ECOG performance status {lo}–{hi}; the profile reports ECOG {ecog}.",
                                ev, quote), True)
    if lo <= ecog <= hi and _single_topic(c.text):
        return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "MET",
                                f"ECOG {ecog} is within the required range {lo}–{hi}.", ev, quote, impact="routine"), True)
    return None


def pregnancy_rules(p: PatientProfile, c: Criterion) -> RuleOutcome | None:
    if c.kind != "exclusion" or not re.search(r"\b(pregnan|breast[- ]?feeding|lactating|nursing)\w*", c.text, re.I):
        return None
    if not _single_topic(c.text) and len(c.text) > 200:
        return None
    if p.demographics.sex.value == "male":
        return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "NOT_APPLICABLE",
                                "This exclusion concerns pregnancy or breastfeeding and does not apply to the profile's sex.",
                                ["Sex male"], None, impact="routine"), True)
    preg = p.history.pregnant_or_breastfeeding.value
    if preg is None:
        return None
    return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "MET" if preg else "NOT_MET",
                            "The profile reports current pregnancy or breastfeeding, which this study excludes." if preg
                            else "The profile reports no current pregnancy or breastfeeding.",
                            [f"pregnant or breastfeeding {'yes' if preg else 'no'}"], None, impact="routine"), True)


_AGE_IN_TEXT = re.compile(r"\b(?:aged?|age)\s*(?:of\s*)?(≥|>=|>|at least)?\s*(\d{1,3})\s*(?:years?)?\s*(?:(?:-|–|to|and)\s*(≤|<=)?\s*(\d{1,3}))?", re.I)


def age_text_rules(p: PatientProfile, c: Criterion) -> RuleOutcome | None:
    age = p.demographics.age_years.value
    if age is None or c.kind not in ("inclusion", "unclassified") or _conditional(c.text):
        return None
    if re.search(r"\b(menopaus|pregnan|childbearing|amenorrh)\w*", c.text, re.I):
        return None  # ages here define menopausal status, not eligibility
    m = _AGE_IN_TEXT.search(_top_line(c.text))
    if not m:
        return None
    lo = int(m.group(2))
    hi = int(m.group(4)) if m.group(4) else None
    if m.group(1) == ">":
        lo += 1
    clause = _clause_around(c.text, m.start(), m.end())
    if _OR.search(clause) or (hi is None and not m.group(1)):
        return None
    ok = age >= lo and (hi is None or age <= hi)
    if not ok:
        return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "NOT_MET",
                                f"The criterion specifies {m.group(0).strip()}; the profile reports age {age}.",
                                [f"Age {age}"], m.group(0).strip()), True)
    if _single_topic(c.text):
        return RuleOutcome(_res(c.criterion_id, c.kind, c.text, "MET",
                                f"Age {age} satisfies '{m.group(0).strip()}'.", [f"Age {age}"], m.group(0).strip(),
                                impact="routine"), True)
    return None


RULES = [biomarker_rules, prior_therapy_rules, stage_rules, ecog_rules, pregnancy_rules, age_text_rules]


def criterion_rules(p: PatientProfile, t: NormalizedTrial) -> dict[str, RuleOutcome]:
    """Run every rule on every criterion; the first definitive blocker (or first definitive result) wins."""
    out: dict[str, RuleOutcome] = {}
    for c in t.criteria:
        outcomes = [o for rule in RULES if (o := rule(p, c)) is not None]
        if not outcomes:
            continue
        blockers = [o for o in outcomes if o.result.is_blocker]
        out[c.criterion_id] = (blockers or outcomes)[0]
    return out
