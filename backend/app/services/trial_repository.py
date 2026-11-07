"""Database cache for normalized trials and live-search results.

Cache policy (explicit):
  * Individual trial records are served from the DB for `trial_cache_ttl_hours` after fetch, then refetched.
  * Search results (list of NCT ids for a query) are reused for `search_cache_ttl_hours`.
  * Every live fetch is logged in trial_data_refreshes with the API's own data timestamp.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import ClinicalTrial, TrialDataRefresh, TrialEligibilityCriterion, TrialLocation
from app.schemas.trial import Contact, Criterion, Intervention, NormalizedTrial, TrialSite
from app.services.trial_normalizer import normalize_study


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def query_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()


def upsert_study(db: Session, raw: dict) -> NormalizedTrial:
    t = normalize_study(raw)
    ttl = timedelta(hours=get_settings().trial_cache_ttl_hours)
    existing = db.get(ClinicalTrial, t.nct_id)
    if existing is not None:
        db.execute(delete(TrialLocation).where(TrialLocation.nct_id == t.nct_id))
        db.execute(delete(TrialEligibilityCriterion).where(TrialEligibilityCriterion.nct_id == t.nct_id))
        row = existing
    else:
        row = ClinicalTrial(nct_id=t.nct_id)
        db.add(row)
    row.brief_title = t.brief_title
    row.official_title = t.official_title
    row.overall_status = t.overall_status
    row.study_type = t.study_type
    row.phases = t.phases
    row.conditions = t.conditions
    row.keywords = t.keywords
    row.brief_summary = t.brief_summary
    row.detailed_description = t.detailed_description
    row.interventions = [i.model_dump() for i in t.interventions]
    row.sponsor = t.sponsor
    row.eligibility_text = t.eligibility_text
    row.sex = t.sex
    row.minimum_age = t.minimum_age
    row.maximum_age = t.maximum_age
    row.min_age_years = t.min_age_years
    row.max_age_years = t.max_age_years
    row.healthy_volunteers = t.healthy_volunteers
    row.enrollment_count = t.enrollment_count
    row.enrollment_type = t.enrollment_type
    row.central_contacts = [c.model_dump() for c in t.central_contacts]
    row.last_update_post_date = t.last_update_post_date
    row.status_verified_date = t.status_verified_date
    row.raw = raw
    row.fetched_at = now_utc()
    row.expires_at = now_utc() + ttl
    db.flush()
    for loc in t.locations:
        db.add(TrialLocation(nct_id=t.nct_id, facility=loc.facility, city=loc.city, state=loc.state, zip=loc.zip,
                             country=loc.country, status=loc.status, lat=loc.lat, lon=loc.lon,
                             contacts=[c.model_dump() for c in loc.contacts]))
    for i, c in enumerate(t.criteria):
        db.add(TrialEligibilityCriterion(nct_id=t.nct_id, criterion_id=c.criterion_id, kind=c.kind,
                                         ordinal=i, text=c.text))
    t.fetched_at = row.fetched_at
    return t


def row_to_trial(row: ClinicalTrial) -> NormalizedTrial:
    return NormalizedTrial(
        nct_id=row.nct_id, brief_title=row.brief_title, official_title=row.official_title,
        overall_status=row.overall_status, study_type=row.study_type, phases=row.phases or [],
        conditions=row.conditions or [], keywords=row.keywords or [], brief_summary=row.brief_summary,
        detailed_description=row.detailed_description,
        interventions=[Intervention(**i) for i in row.interventions or []], sponsor=row.sponsor,
        eligibility_text=row.eligibility_text,
        criteria=[Criterion(criterion_id=c.criterion_id, kind=c.kind, text=c.text) for c in row.criteria],
        sex=row.sex, minimum_age=row.minimum_age, maximum_age=row.maximum_age,
        min_age_years=row.min_age_years, max_age_years=row.max_age_years,
        healthy_volunteers=row.healthy_volunteers, enrollment_count=row.enrollment_count,
        enrollment_type=row.enrollment_type,
        central_contacts=[Contact(**c) for c in row.central_contacts or []],
        locations=[TrialSite(facility=l.facility, city=l.city, state=l.state, zip=l.zip, country=l.country,
                             status=l.status, lat=l.lat, lon=l.lon, contacts=[Contact(**c) for c in l.contacts or []])
                   for l in row.locations],
        last_update_post_date=row.last_update_post_date, status_verified_date=row.status_verified_date,
        fetched_at=row.fetched_at,
    )


def get_cached_trials(db: Session, nct_ids: list[str], *, include_expired: bool = False) -> dict[str, NormalizedTrial]:
    if not nct_ids:
        return {}
    stmt = (select(ClinicalTrial).where(ClinicalTrial.nct_id.in_(nct_ids))
            .options(selectinload(ClinicalTrial.locations), selectinload(ClinicalTrial.criteria)))
    if not include_expired:
        stmt = stmt.where(ClinicalTrial.expires_at > now_utc())
    return {r.nct_id: row_to_trial(r) for r in db.scalars(stmt)}


def get_cached_search(db: Session, qhash: str) -> TrialDataRefresh | None:
    return db.scalars(
        select(TrialDataRefresh)
        .where(TrialDataRefresh.query_hash == qhash, TrialDataRefresh.status == "ok",
               TrialDataRefresh.expires_at > now_utc())
        .order_by(TrialDataRefresh.finished_at.desc()).limit(1)
    ).first()


def start_refresh(db: Session, qhash: str) -> TrialDataRefresh:
    r = TrialDataRefresh(query_hash=qhash, status="running", started_at=now_utc())
    db.add(r)
    db.flush()
    return r


def finish_refresh(db: Session, r: TrialDataRefresh, *, nct_ids: list[str], total: int | None,
                   api_ts: str | None) -> None:
    r.status = "ok"
    r.finished_at = now_utc()
    r.expires_at = r.finished_at + timedelta(hours=get_settings().search_cache_ttl_hours)
    r.nct_ids = nct_ids
    r.total_count = total
    r.api_data_timestamp = api_ts


def fail_refresh(db: Session, r: TrialDataRefresh, error: str) -> None:
    r.status = "error"
    r.finished_at = now_utc()
    r.error = error[:500]


def last_successful_refresh(db: Session) -> TrialDataRefresh | None:
    return db.scalars(select(TrialDataRefresh).where(TrialDataRefresh.status == "ok")
                      .order_by(TrialDataRefresh.finished_at.desc()).limit(1)).first()
