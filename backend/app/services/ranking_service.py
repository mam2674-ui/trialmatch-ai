"""Interpretable relevance scoring.

Relevance answers "how closely does this study's topic match the profile?" — not "is the patient eligible?".
Each component is 0–1 (or None when it does not apply to this profile), and the score is the weighted
mean of applicable components, scaled to 0–100. Weights are fixed and shown to the user.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from app.schemas.match import RelevanceComponent, Relevance
from app.schemas.patient import PatientProfile
from app.schemas.trial import NormalizedTrial, TrialSite
from app.services.eligibility_rules import POS, NEG, RECRUITING
from app.services.geocoding import haversine_miles
from app.services.terminology import biomarker_pattern, therapy_classes_for

WEIGHTS = {
    "condition": 0.25, "semantic": 0.20, "keyword": 0.15, "biomarker": 0.15, "subtype_stage": 0.08,
    "treatment_history": 0.05, "recruiting": 0.06, "geography": 0.06,
}
# A study whose title/conditions name the opposite biomarker status (e.g. "HER2-negative" for a HER2-positive
# profile) is about a different patient population, so its relevance is scaled down explicitly.
BIOMARKER_CONFLICT_PENALTY = 0.6
# PubMedBERT cosine similarities for in-domain text cluster in roughly [0.75, 0.95]; rescale to 0–1.
SEM_LO, SEM_HI = 0.78, 0.95
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+\-]*")
_STOP = {"the", "of", "and", "or", "with", "in", "a", "an", "to", "for", "on", "disease", "patients", "patient",
         "study", "stage", "type", "cancer"}


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


def trial_text(t: NormalizedTrial) -> str:
    return " ".join([t.brief_title, t.official_title or "", " ".join(t.conditions), " ".join(t.keywords),
                     t.brief_summary or "", " ".join(i.name for i in t.interventions),
                     " ".join(c.text for c in t.criteria)])


def query_terms(p: PatientProfile) -> list[str]:
    d = p.diagnosis
    terms = []
    for f in (d.primary_condition, d.subtype, d.histology, d.stage):
        if f.known:
            terms += tokens(str(f.value))
    for b in d.biomarkers:
        terms.append(b.name.lower())
    for t in p.history.prior_treatments:
        terms += tokens(t.name)
    terms += [w for i in p.preferences.treatment_interests for w in tokens(i)]
    if d.metastatic.value:
        terms.append("metastatic")
    return terms


def query_text(p: PatientProfile) -> str:
    """Natural-language query used for the semantic embedding."""
    d = p.diagnosis
    parts = []
    if d.stage.known:
        parts.append(str(d.stage.value))
    if d.metastatic.value:
        parts.append("metastatic")
    for b in d.biomarkers:
        parts.append(f"{b.name} {b.status.replace('_', ' ')}{' ' + b.detail if b.detail else ''}")
    if d.subtype.known:
        parts.append(str(d.subtype.value))
    if d.primary_condition.known:
        parts.append(str(d.primary_condition.value))
    s = " ".join(parts)
    tx = [t.name for t in p.history.prior_treatments]
    if tx:
        s += ". Previously treated with " + ", ".join(tx)
    if p.preferences.treatment_interests:
        s += ". Interested in " + ", ".join(p.preferences.treatment_interests)
    return s or "clinical trial"


def bm25_scores(query: list[str], docs: dict[str, str], k1: float = 1.4, b: float = 0.75) -> dict[str, float]:
    toks = {k: tokens(v) for k, v in docs.items()}
    n = len(toks) or 1
    avgdl = sum(len(v) for v in toks.values()) / n or 1
    df = Counter(t for v in toks.values() for t in set(v))
    q = list(dict.fromkeys(query))
    out = {}
    for k, v in toks.items():
        tf = Counter(v)
        s = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            s += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(v) / avgdl))
        out[k] = s
    return out


def nearest_site(p: PatientProfile, t: NormalizedTrial) -> tuple[TrialSite | None, float | None, int | None]:
    """Nearest site with ClinicalTrials.gov coordinates, preferring sites that are themselves recruiting."""
    loc = p.demographics.location
    if loc.lat is None or loc.lon is None:
        return None, None, None
    radius = p.demographics.travel_radius_miles.value
    scored = [(0 if (s.status or "").upper() in RECRUITING else 1, haversine_miles(loc.lat, loc.lon, s.lat, s.lon), s)
              for s in t.locations if s.lat is not None and s.lon is not None]
    within = sum(1 for _, d, _ in scored if radius and d <= radius) if radius else None
    if not scored:
        return None, None, within
    nearest_recruiting = min(scored, key=lambda x: (x[0], x[1]))
    nearest_any = min(scored, key=lambda x: x[1])
    # Only prefer a recruiting site if it is not dramatically farther than the nearest site.
    pick = nearest_recruiting if nearest_recruiting[1] <= nearest_any[1] + 50 else nearest_any
    d = round(pick[1], 1)
    return pick[2].model_copy(update={"distance_miles": d}), d, within


def _condition_score(p: PatientProfile, t: NormalizedTrial) -> tuple[float | None, str]:
    cond = p.diagnosis.primary_condition.value
    if not cond:
        return None, "No condition in profile"
    c = cond.lower()
    hay = [x.lower() for x in t.conditions] + [t.brief_title.lower()]
    if any(c in h or h in c for h in hay if h):
        return 1.0, f"Study lists '{cond}' among its conditions"
    ct = set(tokens(cond))
    best = max((len(ct & set(tokens(h))) / len(ct) for h in hay if ct), default=0.0)
    if best >= 0.5:
        return 0.6, f"Study conditions partially match '{cond}'"
    return 0.0, f"'{cond}' is not among the study's listed conditions"


def _biomarker_score(p: PatientProfile, t: NormalizedTrial) -> tuple[float | None, str, list[str]]:
    if not p.diagnosis.biomarkers:
        return None, "No biomarkers in profile", []
    headline = " ".join([t.brief_title, t.official_title or "", " ".join(t.conditions), " ".join(t.keywords)])
    full = trial_text(t)
    scores, notes, flags = [], [], []
    tnbc = re.search(r"\b(triple[- ]negative|TNBC)\b", headline, re.I)
    for b in p.diagnosis.biomarkers:
        if tnbc and b.name in ("HER2", "ER", "PR") and b.status in POS:
            scores.append(0.0)
            flags.append(f"Study focuses on triple-negative disease; profile reports {b.name} {b.status}")
            continue
        mention = re.compile(biomarker_pattern(b.name), re.I)
        with_status = re.compile(biomarker_pattern(b.name) + r"(?:\s*-\s*|\s+|)(positive|negative|\+|-(?!\w)|low|"
                                 r"mutat\w*|amplif\w*|wild[- ]?type)", re.I)
        statuses = [m.group(1).lower() for m in with_status.finditer(headline)]
        mentioned_in_headline = bool(mention.search(headline))
        pstat = "pos" if b.status in POS else "neg" if b.status in NEG else None
        opposite = [s for s in statuses if s and (
            (pstat == "pos" and (s in ("negative", "-", "low") or s.startswith("wild")))
            or (pstat == "neg" and (s in ("positive", "+") or s.startswith("amplif") or s.startswith("mutat"))))]
        same = [s for s in statuses if s and s not in opposite]
        if opposite and not same:
            scores.append(0.0)
            word = {"+": "positive", "-": "negative"}.get(opposite[0], opposite[0])
            flags.append(f"Study title/conditions specify {b.name}-{word} disease; profile reports {b.name} {b.status}")
        elif statuses or mentioned_in_headline:
            scores.append(1.0)
            notes.append(f"{b.name} named in the study title/conditions")
        elif mention.search(full):
            scores.append(0.6)
            notes.append(f"{b.name} mentioned in the study record")
        else:
            scores.append(0.2)
    return sum(scores) / len(scores), "; ".join(notes + flags) or "Profile biomarkers not mentioned", flags


def _subtype_stage_score(p: PatientProfile, t: NormalizedTrial, text: str) -> tuple[float | None, str]:
    d = p.diagnosis
    want = []
    if d.subtype.known:
        want += tokens(str(d.subtype.value))
    if d.histology.known:
        want += tokens(str(d.histology.value))
    if d.metastatic.value:
        want.append("metastatic")
    if not want:
        return None, "No subtype/stage detail in profile"
    tt = set(tokens(text))
    hit = [w for w in dict.fromkeys(want) if w in tt]
    return len(hit) / len(set(want)), (f"Mentions {', '.join(hit)}" if hit else "Subtype/stage terms not mentioned")


def _treatment_score(p: PatientProfile, text: str) -> tuple[float | None, str]:
    tx = [t for t in p.history.prior_treatments if t.category not in ("surgery", "radiation")]
    if not tx:
        return None, "No drug therapies in profile"
    low = text.lower()
    hits = []
    for t in tx:
        names = [t.name.lower()] + [c.lower() for c in therapy_classes_for(t.name)]
        if any(n in low for n in names):
            hits.append(t.name)
    return (1.0 if hits else 0.3), (f"Record discusses prior {', '.join(hits)}" if hits else "Prior therapies not discussed")


def score_trial(p: PatientProfile, t: NormalizedTrial, *, semantic: dict | None, keyword: float | None,
                distance: float | None) -> tuple[Relevance, list[str], list[str]]:
    text = trial_text(t)
    comps: list[RelevanceComponent] = []
    why: list[str] = []

    s, d = _condition_score(p, t)
    comps.append(RelevanceComponent(name="condition", score=s, weight=WEIGHTS["condition"], detail=d))
    if s:
        why.append(d)

    if semantic is not None:
        raw = semantic["best"]
        sc = max(0.0, min(1.0, (raw - SEM_LO) / (SEM_HI - SEM_LO)))
        comps.append(RelevanceComponent(name="semantic", score=round(sc, 3), weight=WEIGHTS["semantic"],
                                        detail=f"Biomedical embedding similarity {raw:.3f} (best match: {semantic['best_section'].replace('_', ' ')})"))
    else:
        comps.append(RelevanceComponent(name="semantic", score=None, weight=WEIGHTS["semantic"],
                                        detail="Embeddings disabled or unavailable"))

    comps.append(RelevanceComponent(name="keyword", score=None if keyword is None else round(keyword, 3),
                                    weight=WEIGHTS["keyword"], detail="BM25 keyword overlap with profile terms, relative to other candidates"))

    s, d, flags = _biomarker_score(p, t)
    comps.append(RelevanceComponent(name="biomarker", score=s, weight=WEIGHTS["biomarker"], detail=d))
    if s and s >= 0.6:
        why.append(d)

    s, d = _subtype_stage_score(p, t, text)
    comps.append(RelevanceComponent(name="subtype_stage", score=s, weight=WEIGHTS["subtype_stage"], detail=d))
    if s and s > 0.5:
        why.append(d)

    s, d = _treatment_score(p, text)
    comps.append(RelevanceComponent(name="treatment_history", score=s, weight=WEIGHTS["treatment_history"], detail=d))
    if s == 1.0:
        why.append(d)

    status = t.overall_status or ""
    comps.append(RelevanceComponent(name="recruiting", score=1.0 if status == "RECRUITING" else 0.7 if status in RECRUITING else 0.0,
                                    weight=WEIGHTS["recruiting"], detail=status.replace("_", " ").title() or "Unknown"))

    radius = p.demographics.travel_radius_miles.value
    if distance is None:
        comps.append(RelevanceComponent(name="geography", score=None, weight=WEIGHTS["geography"],
                                        detail="Distance unavailable (location not geocoded or no site coordinates)"))
    else:
        ref = radius or 250
        g = 1.0 if distance <= ref else max(0.0, 1 - (distance - ref) / (ref * 3))
        comps.append(RelevanceComponent(name="geography", score=round(g, 3), weight=WEIGHTS["geography"],
                                        detail=f"Nearest site ≈{distance:.0f} miles"))
        if distance <= ref:
            why.append(f"Site within {ref} miles (≈{distance:.0f} mi)")

    applicable = [c for c in comps if c.score is not None]
    wsum = sum(c.weight for c in applicable) or 1
    score = 100 * sum(c.score * c.weight for c in applicable) / wsum
    penalty, reason = 1.0, None
    if flags:
        penalty, reason = BIOMARKER_CONFLICT_PENALTY, "; ".join(flags)
    return Relevance(score=round(score * penalty, 1), components=comps, penalty_factor=penalty,
                     penalty_reason=reason), why, flags
