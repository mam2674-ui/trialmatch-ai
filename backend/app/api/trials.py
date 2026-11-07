import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import ctgov_http_error, get_ctgov, llm_dep
from app.core.db import get_db
from app.core.ratelimit import rate_limit
from app.schemas.match import (
    CompareRequest, CompareResponse, ExplainRequest, ExplainResponse, MatchRequest, MatchResponse, MatchResult,
)
from app.schemas.patient import PatientProfile
from app.schemas.trial import TrialDetailResponse, TrialSearchRequest, TrialSearchResponse
from app.services import session_service
from app.services import trial_repository as repo
from app.services.clinicaltrials_client import ClinicalTrialsClient, CTGovError, validate_nct_id
from app.services.comparison_service import compare
from app.services.explanation_service import explain_trial
from app.services.llm import DisabledLLM, LLMClient
from app.services.matching_service import build_match_result, run_match

router = APIRouter(prefix="/api", tags=["trials"])


async def load_trial(db: Session, client: ClinicalTrialsClient, nct_id: str) -> tuple:
    nct = validate_nct_id(nct_id)
    cached = repo.get_cached_trials(db, [nct])
    if nct in cached:
        return cached[nct], "cache"
    raw = await client.get_study(nct)
    repo.upsert_study(db, raw)
    db.commit()
    return repo.get_cached_trials(db, [nct])[nct], "live"


@router.post("/trials/search", response_model=TrialSearchResponse, dependencies=[Depends(rate_limit)],
             summary="Search ClinicalTrials.gov (live) and return normalized records")
async def search_trials(req: TrialSearchRequest, db: Session = Depends(get_db),
                        client: ClinicalTrialsClient = Depends(get_ctgov)) -> TrialSearchResponse:
    try:
        version = await client.version()
        result = await client.search(condition=req.condition, term=req.term, intervention=req.intervention,
                                     statuses=req.statuses, max_results=req.max_results)
    except CTGovError as exc:
        raise ctgov_http_error(exc) from exc
    refresh = repo.start_refresh(db, repo.query_hash(req.model_dump()))
    trials = [repo.upsert_study(db, raw) for raw in result.studies]
    repo.finish_refresh(db, refresh, nct_ids=[t.nct_id for t in trials], total=result.total_count,
                        api_ts=version.get("dataTimestamp"))
    db.commit()
    return TrialSearchResponse(total_count=result.total_count, returned=len(trials), trials=trials, data_source="live",
                               refreshed_at=refresh.finished_at, api_data_timestamp=version.get("dataTimestamp"))


@router.post("/trials/match", response_model=MatchResponse, dependencies=[Depends(rate_limit)],
             summary="Rank potentially relevant trials with preliminary eligibility assessments")
async def match_trials(req: MatchRequest, db: Session = Depends(get_db), client: ClinicalTrialsClient = Depends(get_ctgov),
                       llm: LLMClient = Depends(llm_dep)) -> MatchResponse:
    """Assessments are preliminary and never a determination of eligibility. Results are kept in an anonymous
    session that expires automatically (see SESSION_TTL_MINUTES)."""
    if not req.profile.diagnosis.primary_condition.known:
        raise HTTPException(status_code=422, detail="A primary condition is required to search for trials.")
    try:
        return await run_match(db, client, req.profile, llm, max_results=req.max_results, use_ai=req.use_ai)
    except CTGovError as exc:
        raise ctgov_http_error(exc) from exc


@router.get("/trials/{nct_id}", response_model=TrialDetailResponse, summary="Normalized study record")
async def get_trial(nct_id: str, db: Session = Depends(get_db), client: ClinicalTrialsClient = Depends(get_ctgov)):
    try:
        t, source = await load_trial(db, client, nct_id)
    except CTGovError as exc:
        raise ctgov_http_error(exc) from exc
    return TrialDetailResponse(trial=t, data_source=source, refreshed_at=t.fetched_at)


class AssessRequest(BaseModel):
    session_id: uuid.UUID
    profile: PatientProfile


@router.post("/trials/{nct_id}/assess", response_model=MatchResult, dependencies=[Depends(rate_limit)],
             summary="Run (or re-run) AI criterion analysis for one study in a session")
async def assess_one(nct_id: str, req: AssessRequest, db: Session = Depends(get_db),
                     client: ClinicalTrialsClient = Depends(get_ctgov), llm: LLMClient = Depends(llm_dep)) -> MatchResult:
    existing = session_service.get_match(db, req.session_id, validate_nct_id(nct_id))
    if existing is None:
        raise HTTPException(status_code=404, detail="Session expired or study not part of this session.")
    if isinstance(llm, DisabledLLM):
        raise HTTPException(status_code=503, detail="Claude is not configured, so AI criterion analysis is unavailable.")
    try:
        t, _ = await load_trial(db, client, nct_id)
    except CTGovError as exc:
        raise ctgov_http_error(exc) from exc
    result = await build_match_result(req.profile, t, semantic=None, keyword=None, llm=llm, retrieved={t.nct_id},
                                      rank=existing.rank)
    # Keep the relevance computed during the original search (it depends on the whole candidate set).
    result.relevance, result.why_retrieved = existing.relevance, existing.why_retrieved
    session_service.replace_match(db, req.session_id, result)
    return result


@router.get("/sessions/{session_id}/results/{nct_id}", response_model=MatchResult, tags=["sessions"])
async def session_result(session_id: uuid.UUID, nct_id: str, db: Session = Depends(get_db)) -> MatchResult:
    m = session_service.get_match(db, session_id, validate_nct_id(nct_id))
    if m is None:
        raise HTTPException(status_code=404, detail="Session expired or study not part of this session.")
    return m


@router.delete("/sessions/{session_id}", status_code=204, tags=["sessions"], summary="Delete all data for a session now")
async def delete_session(session_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    session_service.delete_session(db, session_id)


@router.post("/trials/{nct_id}/explain", response_model=ExplainResponse, dependencies=[Depends(rate_limit)],
             summary="Evidence-grounded plain-language explanation of one trial")
async def explain(nct_id: str, req: ExplainRequest, db: Session = Depends(get_db),
                  client: ClinicalTrialsClient = Depends(get_ctgov), llm: LLMClient = Depends(llm_dep)) -> ExplainResponse:
    try:
        t, _ = await load_trial(db, client, nct_id)
    except CTGovError as exc:
        raise ctgov_http_error(exc) from exc
    criteria = []
    if req.session_id:
        m = session_service.get_match(db, req.session_id, t.nct_id)
        if m:
            criteria = m.criteria
    return await explain_trial(t, criteria, req.profile, req.mode, llm)


@router.post("/trials/compare", response_model=CompareResponse, summary="Compare 2–4 studies side by side")
async def compare_trials(req: CompareRequest, db: Session = Depends(get_db),
                         client: ClinicalTrialsClient = Depends(get_ctgov)) -> CompareResponse:
    try:
        ids = list(dict.fromkeys(validate_nct_id(i) for i in req.nct_ids))
        if len(ids) < 2:
            raise HTTPException(status_code=422, detail="Select at least two different studies.")
        trials = [(await load_trial(db, client, i))[0] for i in ids]
    except CTGovError as exc:
        raise ctgov_http_error(exc) from exc
    matches = {}
    if req.session_id:
        for i in ids:
            m = session_service.get_match(db, req.session_id, i)
            if m:
                matches[i] = m
    return compare(trials, matches)
