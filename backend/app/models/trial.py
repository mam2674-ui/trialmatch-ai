"""Cached ClinicalTrials.gov records.

`raw` keeps the untouched API payload so every normalized field can be traced back to source.
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ClinicalTrial(Base):
    __tablename__ = "clinical_trials"

    nct_id: Mapped[str] = mapped_column(String(11), primary_key=True)
    brief_title: Mapped[str] = mapped_column(Text)
    official_title: Mapped[str | None] = mapped_column(Text)
    overall_status: Mapped[str | None] = mapped_column(String(40), index=True)
    study_type: Mapped[str | None] = mapped_column(String(40))
    phases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    conditions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    brief_summary: Mapped[str | None] = mapped_column(Text)
    detailed_description: Mapped[str | None] = mapped_column(Text)
    interventions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    sponsor: Mapped[str | None] = mapped_column(Text)
    eligibility_text: Mapped[str | None] = mapped_column(Text)
    sex: Mapped[str | None] = mapped_column(String(10))
    minimum_age: Mapped[str | None] = mapped_column(String(40))
    maximum_age: Mapped[str | None] = mapped_column(String(40))
    min_age_years: Mapped[float | None] = mapped_column(Float)
    max_age_years: Mapped[float | None] = mapped_column(Float)
    healthy_volunteers: Mapped[bool | None] = mapped_column(Boolean)
    enrollment_count: Mapped[int | None] = mapped_column(Integer)
    enrollment_type: Mapped[str | None] = mapped_column(String(20))
    central_contacts: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    last_update_post_date: Mapped[str | None] = mapped_column(String(10))
    status_verified_date: Mapped[str | None] = mapped_column(String(10))
    raw: Mapped[dict] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    locations: Mapped[list["TrialLocation"]] = relationship(
        back_populates="trial", cascade="all, delete-orphan", order_by="TrialLocation.id"
    )
    criteria: Mapped[list["TrialEligibilityCriterion"]] = relationship(
        back_populates="trial", cascade="all, delete-orphan", order_by="TrialEligibilityCriterion.ordinal"
    )


class TrialLocation(Base):
    __tablename__ = "trial_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(ForeignKey("clinical_trials.nct_id", ondelete="CASCADE"), index=True)
    facility: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    zip: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(40))
    # Coordinates are only ever copied from ClinicalTrials.gov's geoPoint; never invented.
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    contacts: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    trial: Mapped[ClinicalTrial] = relationship(back_populates="locations")


class TrialEligibilityCriterion(Base):
    __tablename__ = "trial_eligibility_criteria"
    __table_args__ = (UniqueConstraint("nct_id", "criterion_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(ForeignKey("clinical_trials.nct_id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(12))  # e.g. "I3", "E7", "U1"
    kind: Mapped[str] = mapped_column(String(12))  # inclusion | exclusion | unclassified
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    trial: Mapped[ClinicalTrial] = relationship(back_populates="criteria")


class TrialEmbedding(Base):
    __tablename__ = "trial_embeddings"
    __table_args__ = (
        UniqueConstraint("nct_id", "section", "chunk_index", "model_name"),
        Index(
            "ix_trial_embeddings_hnsw", "embedding", postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(ForeignKey("clinical_trials.nct_id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(30))
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text_hash: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(200))
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrialDataRefresh(Base):
    """Audit log of live ClinicalTrials.gov fetches, doubling as the search-result cache.

    Only a hash of the query is stored, never patient text.
    """

    __tablename__ = "trial_data_refreshes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | error
    total_count: Mapped[int | None] = mapped_column(Integer)
    nct_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    api_data_timestamp: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
