"""Temporary, anonymous matching sessions.

No narrative text is ever stored. Match results (which can contain short excerpts of the structured
profile as evidence) live only until `expires_at` and are purged by `session_service.purge_expired`.
Deleting a session cascades to all of its results and criterion assessments.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class AnonymousMatchingSession(Base):
    __tablename__ = "matching_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Aggregate, non-identifying counters for the methodology dashboard.
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)

    results: Mapped[list["TrialMatchResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class TrialMatchResult(Base):
    __tablename__ = "trial_match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matching_sessions.id", ondelete="CASCADE"), index=True
    )
    nct_id: Mapped[str] = mapped_column(String(11), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(40))
    ai_status: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONB)  # the full MatchResult as served to the client

    session: Mapped[AnonymousMatchingSession] = relationship(back_populates="results")
    assessments: Mapped[list["CriterionAssessment"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", passive_deletes=True
    )


class CriterionAssessment(Base):
    __tablename__ = "criterion_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("trial_match_results.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(12))
    assessment: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))  # rule | llm | llm_rejected
    explanation: Mapped[str] = mapped_column(Text)

    match: Mapped[TrialMatchResult] = relationship(back_populates="assessments")
