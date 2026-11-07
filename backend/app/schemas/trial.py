from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CriterionKind = Literal["inclusion", "exclusion", "unclassified"]


class Contact(BaseModel):
    name: str | None = None
    role: str | None = None
    phone: str | None = None
    phone_ext: str | None = None
    email: str | None = None


class TrialSite(BaseModel):
    facility: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    status: str | None = Field(None, description="Site-level recruitment status, which can differ from the study's")
    lat: float | None = None
    lon: float | None = None
    contacts: list[Contact] = []
    distance_miles: float | None = Field(None, description="Only set when both the patient and the site are geocoded")


class Intervention(BaseModel):
    type: str | None = None
    name: str
    description: str | None = None
    other_names: list[str] = []


class Criterion(BaseModel):
    criterion_id: str
    kind: CriterionKind
    text: str


class NormalizedTrial(BaseModel):
    nct_id: str
    brief_title: str
    official_title: str | None = None
    overall_status: str | None = None
    study_type: str | None = None
    phases: list[str] = []
    conditions: list[str] = []
    keywords: list[str] = []
    brief_summary: str | None = None
    detailed_description: str | None = None
    interventions: list[Intervention] = []
    sponsor: str | None = None
    eligibility_text: str | None = None
    criteria: list[Criterion] = []
    sex: str | None = None
    minimum_age: str | None = None
    maximum_age: str | None = None
    min_age_years: float | None = None
    max_age_years: float | None = None
    healthy_volunteers: bool | None = None
    enrollment_count: int | None = None
    enrollment_type: str | None = None
    central_contacts: list[Contact] = []
    locations: list[TrialSite] = []
    last_update_post_date: str | None = None
    status_verified_date: str | None = None
    fetched_at: datetime | None = None
    url: str = ""

    def model_post_init(self, __context) -> None:
        if not self.url:
            self.url = f"https://clinicaltrials.gov/study/{self.nct_id}"


class TrialSearchRequest(BaseModel):
    condition: str = Field(..., min_length=2, max_length=200)
    term: str | None = Field(None, max_length=200)
    intervention: str | None = Field(None, max_length=200)
    statuses: list[str] = ["RECRUITING", "NOT_YET_RECRUITING"]
    max_results: int = Field(50, ge=1, le=200)


class TrialSearchResponse(BaseModel):
    total_count: int | None
    returned: int
    trials: list[NormalizedTrial]
    data_source: Literal["live", "cache"]
    refreshed_at: datetime | None
    api_data_timestamp: str | None = None


class TrialDetailResponse(BaseModel):
    trial: NormalizedTrial
    data_source: Literal["live", "cache"]
    refreshed_at: datetime | None
