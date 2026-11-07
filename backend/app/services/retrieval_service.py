"""Candidate retrieval: live ClinicalTrials.gov search -> DB cache -> embeddings -> hybrid scores."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.patient import PatientProfile
from app.schemas.trial import NormalizedTrial
from app.services import trial_repository as repo
from app.services.clinicaltrials_client import ClinicalTrialsClient, CTGovUnavailable
from app.services.embedding_service import ensure_embeddings, get_embedder, semantic_scores
from app.services.ranking_service import bm25_scores, query_terms, query_text, trial_text


@dataclass
class SearchSpec:
    condition: str | None
    term: str | None = None
    intervention: str | None = None

    def label(self) -> str:
        parts = [f"condition={self.condition!r}"] if self.condition else []
        if self.term:
            parts.append(f"term={self.term!r}")
        if self.intervention:
            parts.append(f"intervention={self.intervention!r}")
        return ", ".join(parts)


@dataclass
class Candidates:
    trials: list[NormalizedTrial]
    total_available: int | None
    source: str  # live | cache
    refreshed_at: datetime | None
    api_data_timestamp: str | None
    queries: list[str]
    semantic: dict[str, dict] = field(default_factory=dict)
    keyword: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def build_searches(p: PatientProfile) -> list[SearchSpec]:
    """A focused search (condition + biomarker/subtype terms) and a broad one (condition only)."""
    d = p.diagnosis
    cond = d.primary_condition.value
    if not cond:
        return []
    specs = []
    focus = [b.name for b in d.biomarkers if b.status not in ("negative", "wild_type", "not_detected")]
    if d.subtype.known:
        focus.append(str(d.subtype.value))
    if focus:
        specs.append(SearchSpec(condition=cond, term=" OR ".join(f'"{f}"' if " " in f else f for f in focus[:4])))
    specs.append(SearchSpec(condition=cond))
    for interest in p.preferences.treatment_interests[:2]:
        specs.append(SearchSpec(condition=cond, intervention=interest))
    return specs


def statuses_for(p: PatientProfile) -> list[str]:
    if p.preferences.recruiting_only:
        return ["RECRUITING", "NOT_YET_RECRUITING"]
    return ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING"]


async def retrieve_candidates(db: Session, client: ClinicalTrialsClient, p: PatientProfile,
                              max_candidates: int | None = None) -> Candidates:
    s = get_settings()
    max_candidates = max_candidates or s.max_candidates
    specs = build_searches(p)
    if not specs:
        raise ValueError("A primary condition is required to search for trials.")
    loc = p.demographics.location
    radius = p.demographics.travel_radius_miles.value
    geo = (round(loc.lat, 2), round(loc.lon, 2), radius) if (loc.lat is not None and radius) else None
    statuses = statuses_for(p)

    ordered_ids: list[str] = []
    total: int | None = None
    sources: set[str] = set()
    refreshed_at: datetime | None = None
    api_ts: str | None = None
    per_query = max(10, max_candidates // len(specs) + 10)

    try:
        version = await client.version()
        api_ts = version.get("dataTimestamp")
    except CTGovUnavailable:
        version = None

    for spec in specs:
        params = {"cond": spec.condition, "term": spec.term, "intr": spec.intervention, "statuses": statuses,
                  "geo": geo, "n": per_query}
        qh = repo.query_hash(params)
        cached = repo.get_cached_search(db, qh)
        if cached is not None:
            cached_trials = repo.get_cached_trials(db, cached.nct_ids)
            if len(cached_trials) == len(cached.nct_ids):
                ids = cached.nct_ids
                sources.add("cache")
                refreshed_at = max(filter(None, [refreshed_at, cached.finished_at]), default=None)
                total = max(filter(None, [total, cached.total_count]), default=None)
                ordered_ids += [i for i in ids if i not in ordered_ids]
                continue
        if version is None:
            raise CTGovUnavailable("ClinicalTrials.gov is not reachable and no cached results exist for this search.")
        refresh = repo.start_refresh(db, qh)
        try:
            result = await client.search(condition=spec.condition, term=spec.term, intervention=spec.intervention,
                                         statuses=statuses, geo=geo, max_results=per_query)
        except CTGovUnavailable as exc:
            repo.fail_refresh(db, refresh, str(exc))
            db.commit()
            raise
        ids = []
        for raw in result.studies:
            t = repo.upsert_study(db, raw)
            ids.append(t.nct_id)
        repo.finish_refresh(db, refresh, nct_ids=ids, total=result.total_count, api_ts=api_ts)
        db.commit()
        sources.add("live")
        refreshed_at = refresh.finished_at
        # Different queries overlap; the largest single total is the honest lower bound of what's available.
        total = max(filter(None, [total, result.total_count]), default=None)
        ordered_ids += [i for i in ids if i not in ordered_ids]
        if len(ordered_ids) >= max_candidates:
            break

    ordered_ids = ordered_ids[:max_candidates]
    trials_by_id = repo.get_cached_trials(db, ordered_ids, include_expired=True)
    trials = [trials_by_id[i] for i in ordered_ids if i in trials_by_id]
    cands = Candidates(trials=trials, total_available=total, source="live" if "live" in sources else "cache",
                       refreshed_at=refreshed_at, api_data_timestamp=api_ts, queries=[sp.label() for sp in specs])

    # Keyword relevance (BM25 over the candidate set), normalized to 0–1.
    bm = bm25_scores(query_terms(p), {t.nct_id: trial_text(t) for t in trials})
    top = max(bm.values(), default=0) or 1
    cands.keyword = {k: v / top for k, v in bm.items()}

    # Semantic relevance via pgvector.
    embedder = get_embedder()
    if embedder is not None and trials:
        try:
            await ensure_embeddings(db, trials, embedder)
            db.commit()
            qv = (await asyncio.to_thread(embedder.encode, [query_text(p)]))[0]
            cands.semantic = semantic_scores(db, qv, [t.nct_id for t in trials], embedder.model_name)
        except Exception as exc:  # embedding failures degrade to keyword-only ranking, visibly
            db.rollback()
            cands.warnings.append(f"Semantic search unavailable ({type(exc).__name__}); ranking used keyword and "
                                  "metadata signals only.")
    elif embedder is None:
        cands.warnings.append("Semantic embeddings are disabled; ranking used keyword and metadata signals only.")
    return cands
