from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_ctgov
from app.core.config import get_settings
from app.core.db import get_db
from app.models import ClinicalTrial, TrialDataRefresh, TrialEmbedding
from app.services import session_service
from app.services.clinicaltrials_client import ClinicalTrialsClient, CTGovError
from app.services.embedding_service import get_embedder
from app.services.llm import DisabledLLM, get_llm
from app.services.ranking_service import WEIGHTS
from app.services.trial_repository import last_successful_refresh

router = APIRouter(prefix="/api", tags=["meta"])


class Health(BaseModel):
    status: str
    database: str
    pgvector: str
    clinicaltrials_gov: str
    clinicaltrials_gov_data_timestamp: str | None
    ai: str
    ai_auth: str | None
    ai_model: str | None
    embeddings: str
    embedding_model: str | None


@router.get("/health", response_model=Health, summary="Service health (no secrets)")
async def health(db: Session = Depends(get_db), client: ClinicalTrialsClient = Depends(get_ctgov)) -> Health:
    s = get_settings()
    try:
        db.execute(text("SELECT 1"))
        dbs = "ok"
        vec = "ok" if db.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")) else "missing"
    except Exception:
        dbs, vec = "error", "unknown"
    try:
        v = await client.version()
        ct, ts = "ok", v.get("dataTimestamp")
    except CTGovError:
        ct, ts = "unreachable", None
    llm = get_llm()
    ai = "disabled" if isinstance(llm, DisabledLLM) else "configured"
    emb = get_embedder()
    overall = "ok" if dbs == "ok" and ct == "ok" else "degraded"
    return Health(status=overall, database=dbs, pgvector=vec, clinicaltrials_gov=ct, clinicaltrials_gov_data_timestamp=ts,
                  ai=ai, ai_auth=None if ai == "disabled" else s.llm_auth_mode,
                  ai_model=None if ai == "disabled" else s.claude_model,
                  embeddings="enabled" if emb else "disabled", embedding_model=s.embedding_model if emb else None)


class MethodologyStats(BaseModel):
    cached_trials: int
    embedded_chunks: int
    live_refreshes: int
    failed_refreshes: int
    last_successful_refresh: datetime | None
    clinicaltrials_gov_data_timestamp: str | None
    active_sessions: int
    session_ttl_minutes: int
    trial_cache_ttl_hours: int
    search_cache_ttl_hours: int
    relevance_weights: dict[str, float]
    ai_model: str | None
    embedding_model: str | None
    usage: dict


@router.get("/methodology/stats", response_model=MethodologyStats, summary="Aggregate, non-identifying system statistics")
async def methodology_stats(db: Session = Depends(get_db)) -> MethodologyStats:
    s = get_settings()
    last = last_successful_refresh(db)
    llm = get_llm()
    return MethodologyStats(
        cached_trials=db.scalar(select(func.count()).select_from(ClinicalTrial)) or 0,
        embedded_chunks=db.scalar(select(func.count()).select_from(TrialEmbedding)) or 0,
        live_refreshes=db.scalar(select(func.count()).select_from(TrialDataRefresh).where(TrialDataRefresh.status == "ok")) or 0,
        failed_refreshes=db.scalar(select(func.count()).select_from(TrialDataRefresh).where(TrialDataRefresh.status == "error")) or 0,
        last_successful_refresh=last.finished_at if last else None,
        clinicaltrials_gov_data_timestamp=last.api_data_timestamp if last else None,
        active_sessions=session_service.active_session_count(db),
        session_ttl_minutes=s.session_ttl_minutes, trial_cache_ttl_hours=s.trial_cache_ttl_hours,
        search_cache_ttl_hours=s.search_cache_ttl_hours, relevance_weights=WEIGHTS,
        ai_model=None if isinstance(llm, DisabledLLM) else s.claude_model,
        embedding_model=s.embedding_model if s.embeddings_enabled else None,
        usage={"llm_calls": llm.usage.calls, "input_tokens": llm.usage.input_tokens,
               "output_tokens": llm.usage.output_tokens, "estimated_cost_usd": llm.usage.cost_usd},
    )
