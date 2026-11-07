"""Structured patient profile.

Every clinical fact carries provenance:
  * patient_provided  – entered or confirmed by the user in the structured form
  * model_extracted   – extracted by Claude from the narrative, with a verbatim evidence quote
  * rule_extracted    – extracted by deterministic regex rules from the narrative
  * unknown           – not provided; never treated as evidence of eligibility
"""

from __future__ import annotations

import re
from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.terminology import normalize_biomarker_name, normalize_lab

Source = Literal["patient_provided", "model_extracted", "rule_extracted", "unknown"]
T = TypeVar("T")


class Fact(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    source: Source = "unknown"
    evidence: str | None = Field(None, max_length=500, description="Verbatim quote from the narrative")

    @model_validator(mode="after")
    def _unknown_has_no_value(self):
        if self.value is None:
            self.source = "unknown"
        elif self.source == "unknown":
            # A value with no stated provenance is treated as user-entered (structured form).
            self.source = "patient_provided"
        return self

    @property
    def known(self) -> bool:
        return self.value is not None


class Location(BaseModel):
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=100)
    source: Source = "unknown"
    evidence: str | None = None
    # Filled only by the geocoder; never by the model.
    lat: float | None = None
    lon: float | None = None
    geocoded_label: str | None = None

    @property
    def known(self) -> bool:
        return any([self.city, self.state, self.postal_code, self.country])

    def query_string(self) -> str:
        return ", ".join(p for p in [self.city, self.state, self.postal_code, self.country] if p)


class Demographics(BaseModel):
    age_years: Fact[int] = Fact()
    sex: Fact[Literal["female", "male"]] = Fact()
    location: Location = Location()
    travel_radius_miles: Fact[int] = Fact()

    @field_validator("age_years")
    @classmethod
    def _age_range(cls, v: Fact[int]):
        if v.value is not None and not 0 <= v.value <= 120:
            raise ValueError("age must be between 0 and 120 years")
        return v

    @field_validator("travel_radius_miles")
    @classmethod
    def _radius(cls, v: Fact[int]):
        if v.value is not None and not 1 <= v.value <= 5000:
            raise ValueError("travel radius must be between 1 and 5000 miles")
        return v


BiomarkerStatus = Literal["positive", "negative", "mutated", "wild_type", "amplified", "not_detected", "other"]


class Biomarker(BaseModel):
    name: str = Field(..., max_length=60)
    status: BiomarkerStatus
    detail: str | None = Field(None, max_length=120, description="e.g. 'exon 19 deletion', 'IHC 3+'")
    source: Source = "patient_provided"
    evidence: str | None = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_biomarker_name(v)


class Treatment(BaseModel):
    name: str = Field(..., max_length=120)
    category: str | None = Field(None, max_length=60, description="e.g. chemotherapy, surgery, targeted therapy")
    status: Literal["completed", "ongoing", "planned", "unknown"] = "unknown"
    # Whether the disease progressed on/after this treatment. Never inferred.
    progression: Literal["yes", "no", "unknown"] = "unknown"
    source: Source = "patient_provided"
    evidence: str | None = Field(None, max_length=500)


class LabValue(BaseModel):
    name: str = Field(..., max_length=60)
    value: float
    unit: str = Field(..., max_length=30)
    measured_on: date | None = None
    source: Source = "patient_provided"
    evidence: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _validate_units(self):
        self.name, self.unit = normalize_lab(self.name, self.unit, self.value)
        if self.measured_on and self.measured_on > date.today():
            raise ValueError("lab date cannot be in the future")
        return self


class Diagnosis(BaseModel):
    primary_condition: Fact[str] = Fact()
    subtype: Fact[str] = Fact()
    stage: Fact[str] = Fact()
    diagnosis_date: Fact[date] = Fact()
    histology: Fact[str] = Fact()
    metastatic: Fact[bool] = Fact()
    biomarkers: list[Biomarker] = Field(default_factory=list, max_length=30)
    findings: list[Fact[str]] = Field(default_factory=list, max_length=20)

    @field_validator("diagnosis_date")
    @classmethod
    def _not_future(cls, v: Fact[date]):
        if v.value and v.value > date.today():
            raise ValueError("diagnosis date cannot be in the future")
        return v

    @field_validator("stage")
    @classmethod
    def _stage(cls, v: Fact[str]):
        if v.value:
            v.value = normalize_stage(v.value)
        return v


class MedicalHistory(BaseModel):
    prior_treatments: list[Treatment] = Field(default_factory=list, max_length=40)
    current_medications: list[Fact[str]] = Field(default_factory=list, max_length=40)
    comorbidities: list[Fact[str]] = Field(default_factory=list, max_length=30)
    ecog_performance_status: Fact[int] = Fact()
    labs: list[LabValue] = Field(default_factory=list, max_length=40)
    prior_trial_participation: Fact[bool] = Fact()
    pregnant_or_breastfeeding: Fact[bool] = Fact()

    @field_validator("ecog_performance_status")
    @classmethod
    def _ecog(cls, v: Fact[int]):
        if v.value is not None and not 0 <= v.value <= 5:
            raise ValueError("ECOG performance status must be 0–5")
        return v


class Preferences(BaseModel):
    willing_to_travel: bool | None = None
    treatment_interests: list[str] = Field(default_factory=list, max_length=10)
    preferred_phases: list[Literal["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"]] = Field(
        default_factory=list
    )
    recruiting_only: bool = True
    remote_ok: bool | None = None


class Conflict(BaseModel):
    field: str
    description: str


class PatientProfile(BaseModel):
    demographics: Demographics = Demographics()
    diagnosis: Diagnosis = Diagnosis()
    history: MedicalHistory = MedicalHistory()
    preferences: Preferences = Preferences()
    conflicts: list[Conflict] = Field(default_factory=list)
    is_demo: bool = False

    def known_facts_text(self) -> str:
        """Flattened text of every known fact, used to verify that model-cited patient evidence is real."""
        parts: list[str] = []
        d, dx, h = self.demographics, self.diagnosis, self.history
        if d.age_years.known:
            parts += [f"{d.age_years.value} years old", f"age {d.age_years.value}"]
        if d.sex.known:
            parts.append(f"sex {d.sex.value}")
        if d.location.known:
            parts.append(d.location.query_string())
        for f in (dx.primary_condition, dx.subtype, dx.stage, dx.histology):
            if f.known:
                parts.append(str(f.value))
        if dx.metastatic.known:
            parts.append("metastatic" if dx.metastatic.value else "not metastatic")
        for b in dx.biomarkers:
            parts.append(f"{b.name} {b.status} {b.detail or ''}".strip())
        parts += [str(f.value) for f in dx.findings if f.known]
        for t in h.prior_treatments:
            parts.append(f"{t.name} {t.category or ''} {t.status} progression {t.progression}")
        parts += [str(f.value) for f in h.current_medications + h.comorbidities if f.known]
        if h.ecog_performance_status.known:
            parts.append(f"ECOG {h.ecog_performance_status.value}")
        for lab in h.labs:
            parts.append(f"{lab.name} {lab.value:g} {lab.unit}")
        for f, label in ((h.prior_trial_participation, "prior trial participation"),
                         (h.pregnant_or_breastfeeding, "pregnant or breastfeeding")):
            if f.known:
                parts.append(f"{label} {'yes' if f.value else 'no'}")
        return "\n".join(p for p in parts if p)


_STAGE_RE = re.compile(r"^(?:stage\s*)?(iv|i{1,3}|0|[1-4])\s*([abc]\d?)?$", re.I)
_ARABIC_TO_ROMAN = {"0": "0", "1": "I", "2": "II", "3": "III", "4": "IV"}


def normalize_stage(raw: str) -> str:
    """'stage 2b' -> 'Stage IIB'; free text that is not a stage label is kept verbatim."""
    s = raw.strip()
    m = _STAGE_RE.match(s)
    if not m:
        return s
    base = _ARABIC_TO_ROMAN.get(m.group(1).upper(), m.group(1).upper())
    return f"Stage {base}{(m.group(2) or '').upper()}"


def stage_number(stage: str | None) -> int | None:
    """'Stage IIB' -> 2. Returns None for anything that is not a recognizable stage."""
    if not stage:
        return None
    m = re.match(r"^stage\s+(iv|i{1,3}|0)(?![iv])", stage, re.I)
    if not m:
        return None
    return {"0": 0, "I": 1, "II": 2, "III": 3, "IV": 4}[m.group(1).upper()]


# ---------- API request/response models ----------


class ParseRequest(BaseModel):
    narrative: str = Field(..., min_length=10, max_length=4000)
    demo: bool = False


class ParseResponse(BaseModel):
    profile: PatientProfile
    extraction_method: Literal["claude", "rules"]
    warnings: list[str] = []
    dropped_unverified: list[str] = Field(
        default_factory=list, description="Model-extracted values discarded because their evidence quote was not in the text"
    )
