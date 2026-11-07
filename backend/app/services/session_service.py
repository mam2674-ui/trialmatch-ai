"""Anonymous matching sessions with strict expiry. No narrative text is ever persisted."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AnonymousMatchingSession, CriterionAssessment, TrialMatchResult
from app.schemas.match import MatchResult
from app.services.trial_repository import now_utc


def purge_expired(db: Session) -> int:
    res = db.execute(delete(AnonymousMatchingSession).where(AnonymousMatchingSession.expires_at <= now_utc()))
    db.commit()
    return res.rowcount or 0


def create_session(db: Session, results: list[MatchResult], stats: dict) -> AnonymousMatchingSession:
    s = AnonymousMatchingSession(id=uuid.uuid4(), expires_at=now_utc() + timedelta(minutes=get_settings().session_ttl_minutes),
                                 stats=stats)
    db.add(s)
    db.flush()
    for r in results:
        row = TrialMatchResult(session_id=s.id, nct_id=r.trial.nct_id, rank=r.rank, category=r.eligibility.category,
                               ai_status=r.ai_status, payload=r.model_dump(mode="json"))
        db.add(row)
        db.flush()
        for c in r.criteria:
            db.add(CriterionAssessment(match_id=row.id, criterion_id=c.criterion_id, kind=c.kind,
                                       assessment=c.assessment, source=c.source, explanation=c.explanation[:2000]))
    db.commit()
    return s


def get_session(db: Session, session_id: uuid.UUID) -> AnonymousMatchingSession | None:
    s = db.get(AnonymousMatchingSession, session_id)
    if s is None or s.expires_at <= now_utc():
        return None
    return s


def get_match(db: Session, session_id: uuid.UUID, nct_id: str) -> MatchResult | None:
    if get_session(db, session_id) is None:
        return None
    row = db.scalars(select(TrialMatchResult).where(TrialMatchResult.session_id == session_id,
                                                    TrialMatchResult.nct_id == nct_id)).first()
    return MatchResult.model_validate(row.payload) if row else None


def replace_match(db: Session, session_id: uuid.UUID, result: MatchResult) -> None:
    row = db.scalars(select(TrialMatchResult).where(TrialMatchResult.session_id == session_id,
                                                    TrialMatchResult.nct_id == result.trial.nct_id)).first()
    if row is None:
        return
    row.payload = result.model_dump(mode="json")
    row.category = result.eligibility.category
    row.ai_status = result.ai_status
    db.execute(delete(CriterionAssessment).where(CriterionAssessment.match_id == row.id))
    for c in result.criteria:
        db.add(CriterionAssessment(match_id=row.id, criterion_id=c.criterion_id, kind=c.kind, assessment=c.assessment,
                                   source=c.source, explanation=c.explanation[:2000]))
    db.commit()


def delete_session(db: Session, session_id: uuid.UUID) -> bool:
    res = db.execute(delete(AnonymousMatchingSession).where(AnonymousMatchingSession.id == session_id))
    db.commit()
    return bool(res.rowcount)


def active_session_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AnonymousMatchingSession)
                     .where(AnonymousMatchingSession.expires_at > now_utc())) or 0
