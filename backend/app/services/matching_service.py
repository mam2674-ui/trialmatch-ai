"""End-to-end matching orchestration.

profile -> geocode -> retrieve candidates (live API + cache + embeddings) -> relevance scores
        -> deterministic checks on all candidates -> Claude analysis on the top-K non-blocked candidates
        -> categorize -> order (hard blockers always sink below other results) -> follow-up questions
        -> store in a short-lived anonymous session.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.match import DataProvenance, MatchResponse, MatchResult, MatchStats
from app.schemas.patient import PatientProfile
from app.schemas.trial import NormalizedTrial
from app.services import session_service
from app.services.clinicaltrials_client import ClinicalTrialsClient
from app.services.eligibility_engine import assess_trial
from app.services.eligibility_rules import structured_checks
from app.services.followup_service import generate_questions
from app.services.geocoding import geocode
from app.services.llm import DisabledLLM, LLMClient
from app.services.ranking_service import nearest_site, score_trial
from app.services.retrieval_service import retrieve_candidates

CATEGORY_ORDER = {"POTENTIAL_MATCH": 0, "REQUIRES_CLINICAL_REVIEW": 1, "NEEDS_MORE_INFORMATION": 2,
                  "POTENTIALLY_INELIGIBLE": 3}


async def build_match_result(p: PatientProfile, t: NormalizedTrial, *, semantic: dict | None, keyword: float | None,
                             llm: LLMClient | None, retrieved: set[str] | None, rank: int = 0) -> MatchResult:
    site, dist, within = nearest_site(p, t)
    relevance, why, flags = score_trial(p, t, semantic=semantic, keyword=keyword, distance=dist)
    a = await assess_trial(p, t, llm, retrieved=retrieved)
    questions = [c.question for c in a["criteria"] if c.question and c.assessment == "UNKNOWN" and c.impact == "high"]
    return MatchResult(
        rank=rank, trial=t, relevance=relevance, why_retrieved=why + [f"⚠ {f}" for f in flags] or
        ["Returned by the ClinicalTrials.gov search for the profile's condition"],
        eligibility=a["eligibility"], criteria=a["criteria"], completeness=a["completeness"],
        questions=list(dict.fromkeys(questions))[:5], nearest_site=site, distance_miles=dist,
        sites_within_radius=within, ai_status=a["ai_status"], ai_note=a["ai_note"],
    )


def order_results(results: list[MatchResult]) -> list[MatchResult]:
    """Relevance order, but explicit blockers always rank below non-blocked studies.

    High semantic similarity can therefore never lift a study with an identified exclusion above one without.
    """
    results.sort(key=lambda r: (r.eligibility.category == "POTENTIALLY_INELIGIBLE", -r.relevance.score))
    for i, r in enumerate(results, 1):
        r.rank = i
    return results


async def run_match(db: Session, client: ClinicalTrialsClient, profile: PatientProfile, llm: LLMClient, *,
                    max_results: int = 25, use_ai: bool = True) -> MatchResponse:
    s = get_settings()
    warnings: list[str] = []
    session_service.purge_expired(db)

    loc = profile.demographics.location
    if loc.known and loc.lat is None:
        geocoded = await geocode(loc)
        if geocoded.lat is None:
            warnings.append(f"Could not geocode '{loc.query_string()}'; distances are not shown and no distance filter was applied.")
        profile = profile.model_copy(update={"demographics": profile.demographics.model_copy(update={"location": geocoded})})

    cands = await retrieve_candidates(db, client, profile)
    warnings += cands.warnings
    retrieved = {t.nct_id for t in cands.trials}

    # Pass 1: relevance + deterministic checks for every candidate (cheap).
    prelim = []
    for t in cands.trials:
        site, dist, _ = nearest_site(profile, t)
        rel, _, _ = score_trial(profile, t, semantic=cands.semantic.get(t.nct_id), keyword=cands.keyword.get(t.nct_id),
                                distance=dist)
        blocked = any(r.is_blocker for r in structured_checks(profile, t))
        prelim.append((blocked, -rel.score, t))
    prelim.sort(key=lambda x: (x[0], x[1]))
    selected = [t for *_, t in prelim[:max_results]]

    ai_llm: LLMClient | None = llm if (use_ai and not isinstance(llm, DisabledLLM)) else None
    ai_ids = {t.nct_id for t in selected[: s.llm_max_trials_per_match]} if ai_llm else set()
    if use_ai and isinstance(llm, DisabledLLM):
        warnings.append("Claude is not configured, so inclusion/exclusion criteria were not analyzed by AI. "
                        "Results show retrieved studies with deterministic checks only.")

    results = await asyncio.gather(*[
        build_match_result(profile, t, semantic=cands.semantic.get(t.nct_id), keyword=cands.keyword.get(t.nct_id),
                           llm=ai_llm if t.nct_id in ai_ids else None, retrieved=retrieved)
        for t in selected
    ])
    for r in results:
        if r.ai_status == "not_run" and ai_llm and r.eligibility.category != "POTENTIALLY_INELIGIBLE":
            r.ai_note = r.ai_note or (f"AI analysis is run automatically for the top {s.llm_max_trials_per_match} "
                                      "results; use 'Analyze criteria' to run it for this study.")
    results = order_results(list(results))
    if any(r.ai_status == "unavailable" for r in results):
        warnings.append("Claude became unavailable during analysis; affected studies show deterministic checks only.")

    stats = MatchStats(
        candidates_retrieved=len(cands.trials), total_available=cands.total_available,
        studies_analyzed=len(results), ai_analyzed=sum(r.ai_status == "ok" for r in results),
        potential_matches=sum(r.eligibility.category == "POTENTIAL_MATCH" for r in results),
        unresolved=sum(r.eligibility.category in ("NEEDS_MORE_INFORMATION", "REQUIRES_CLINICAL_REVIEW") for r in results),
        conflicts=sum(r.eligibility.category == "POTENTIALLY_INELIGIBLE" for r in results),
        ineligible=sum(r.eligibility.category == "POTENTIALLY_INELIGIBLE" for r in results),
    )
    session = session_service.create_session(db, results, stats.model_dump())
    return MatchResponse(
        session_id=session.id, expires_at=session.expires_at, results=results,
        questions=generate_questions(profile, results), stats=stats,
        data=DataProvenance(source=cands.source, refreshed_at=cands.refreshed_at,
                            api_data_timestamp=cands.api_data_timestamp, queries=cands.queries),
        profile_used=profile, warnings=warnings, ai_enabled=not isinstance(llm, DisabledLLM),
    )
