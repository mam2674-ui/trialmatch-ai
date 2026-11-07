from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.patient import PatientProfile
from app.schemas.trial import NormalizedTrial, TrialSite

Assessment = Literal["MET", "NOT_MET", "UNKNOWN", "NOT_APPLICABLE"]
Category = Literal["POTENTIAL_MATCH", "NEEDS_MORE_INFORMATION", "POTENTIALLY_INELIGIBLE", "REQUIRES_CLINICAL_REVIEW"]
UnknownReason = Literal["missing_patient_info", "requires_screening_test", "ambiguous_criterion",
                        "requires_clinical_judgment"]
AIStatus = Literal["ok", "unavailable", "validation_failed", "not_run", "error"]

CATEGORY_LABELS = {
    "POTENTIAL_MATCH": "Potential match",
    "NEEDS_MORE_INFORMATION": "Needs more information",
    "POTENTIALLY_INELIGIBLE": "Potentially ineligible",
    "REQUIRES_CLINICAL_REVIEW": "Requires clinical review",
}

DISCLAIMER = (
    "TrialMatch AI provides preliminary, informational screening only. It does not determine eligibility "
    "for any clinical trial and is not medical advice. Final eligibility is established only by the study's "
    "research team. Discuss any trial with your doctor."
)


class CriterionResult(BaseModel):
    criterion_id: str = Field(description="I#/E#/U# for trial criteria; AGE/SEX/STATUS for structured fields")
    kind: Literal["inclusion", "exclusion", "unclassified", "structured"]
    criterion_text: str = Field(description="Verbatim from the trial record")
    assessment: Assessment
    is_blocker: bool = Field(description="Inclusion NOT_MET or exclusion MET")
    patient_evidence: list[str] = []
    trial_evidence: str | None = None
    explanation: str
    needs_info: bool = False
    unknown_reason: UnknownReason | None = None
    impact: Literal["high", "routine"] = "routine"
    question: str | None = None
    source: Literal["rule", "claude", "not_assessed"]
    validation_notes: list[str] = []


class RelevanceComponent(BaseModel):
    name: str
    score: float | None = Field(description="0–1, or null when not applicable to this profile")
    weight: float
    detail: str


class Relevance(BaseModel):
    score: float = Field(description="0–100 weighted mean of applicable components, times any penalty")
    components: list[RelevanceComponent]
    penalty_factor: float = 1.0
    penalty_reason: str | None = None
    note: str = "Search relevance only: how closely this study's topic matches the profile. It is not a probability of eligibility."


class Completeness(BaseModel):
    total_criteria: int
    assessed: int
    unknown: int
    not_assessed: int
    fraction_assessed: float


class EligibilitySummary(BaseModel):
    category: Category
    label: str
    headline: str
    explanation: str
    explanation_source: Literal["claude", "rules"]
    blockers: list[str] = []
    met: list[str] = []
    unknown: list[str] = []
    review: list[str] = []


class MatchResult(BaseModel):
    rank: int
    trial: NormalizedTrial
    relevance: Relevance
    why_retrieved: list[str]
    eligibility: EligibilitySummary
    criteria: list[CriterionResult]
    completeness: Completeness
    questions: list[str] = []
    nearest_site: TrialSite | None = None
    distance_miles: float | None = None
    sites_within_radius: int | None = None
    ai_status: AIStatus
    ai_note: str | None = None


class AnswerOption(BaseModel):
    label: str
    value: Literal["yes", "no", "not_sure"]


class FollowUpQuestion(BaseModel):
    id: str
    question: str
    why: str
    options: list[AnswerOption] = [AnswerOption(label="Yes", value="yes"), AnswerOption(label="No", value="no"),
                                   AnswerOption(label="Not sure", value="not_sure")]
    patch: dict = Field(description="How an answer updates the structured profile (applied client- or server-side)")
    affected_trials: list[str]
    priority: float


class MatchStats(BaseModel):
    candidates_retrieved: int
    total_available: int | None
    studies_analyzed: int
    ai_analyzed: int
    potential_matches: int
    unresolved: int
    conflicts: int
    ineligible: int


class DataProvenance(BaseModel):
    source: Literal["live", "cache"]
    refreshed_at: datetime | None
    api_data_timestamp: str | None
    queries: list[str]


class MatchRequest(BaseModel):
    profile: PatientProfile
    max_results: int = Field(25, ge=1, le=60)
    use_ai: bool = True


class MatchResponse(BaseModel):
    session_id: uuid.UUID
    expires_at: datetime
    results: list[MatchResult]
    questions: list[FollowUpQuestion]
    stats: MatchStats
    data: DataProvenance
    profile_used: PatientProfile
    warnings: list[str] = []
    ai_enabled: bool
    disclaimer: str = DISCLAIMER


class ApplyAnswerRequest(BaseModel):
    profile: PatientProfile
    question: FollowUpQuestion
    answer: Literal["yes", "no", "not_sure"]


class ExplainRequest(BaseModel):
    session_id: uuid.UUID | None = None
    profile: PatientProfile | None = None
    mode: Literal["patient", "clinical"] = "patient"


class ExplanationSection(BaseModel):
    heading: str
    body: str
    cited_criteria: list[str] = []


class ExplainResponse(BaseModel):
    nct_id: str
    mode: Literal["patient", "clinical"]
    sections: list[ExplanationSection]
    questions_for_team: list[str]
    glossary: dict[str, str]
    source: Literal["claude", "rules"]
    validation_notes: list[str] = []
    disclaimer: str = DISCLAIMER


class CompareRequest(BaseModel):
    nct_ids: list[str] = Field(..., min_length=2, max_length=4)
    session_id: uuid.UUID | None = None


class CompareRow(BaseModel):
    field: str
    values: dict[str, str | list[str] | None]


class CompareResponse(BaseModel):
    nct_ids: list[str]
    rows: list[CompareRow]
    note: str = ("Comparison of study characteristics and preliminary eligibility only. Studies are not ranked by "
                 "expected effectiveness, and nothing here suggests one treatment is better than another.")
