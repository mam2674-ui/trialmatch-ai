"""Second validation layer for model output. Nothing the model says reaches the user unchecked.

Checks (per the grounding requirements):
  1. The NCT id is the trial that was actually sent (and is among retrieved records).
  2. Every cited criterion id exists in the source record.
  3. Quoted trial evidence is present verbatim (normalized) in that criterion / the record.
  4. Every patient fact cited is present in the verified patient profile.
  5. Definitive assessments (MET/NOT_MET) must cite supporting patient evidence; UNKNOWN must say why.
  6. Citations embedded in free-text explanations ("[I3]") must refer to real criteria.
Failures downgrade the claim to UNKNOWN (never upgrade), and are recorded as validation notes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.schemas.trial import NormalizedTrial

_STOP = {"the", "a", "an", "of", "and", "or", "with", "to", "in", "on", "for", "is", "was", "has", "have", "had",
         "patient", "patients", "profile", "reports", "reported", "status", "years", "year", "old", "age", "no",
         "yes", "prior", "treatment", "by", "at", "as", "from", "be", "been", "not", "unknown", "progression"}
CITATION_RE = re.compile(r"\[([IEU]\d{1,3}|AGE|SEX|STATUS)\]")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("“", '"').replace("”", '"').replace("≥", ">=").replace("≤", "<=")
    s = re.sub(r"[‐-―−]", "-", s)
    s = re.sub(r"^\s*[-*•]\s*", "", s, flags=re.M)
    s = re.sub(r"[^\w%<>=+./-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_in(quote: str | None, source: str) -> bool:
    if not quote or len(quote.strip()) < 3:
        return False
    q, src = norm(quote).strip(" ."), norm(source)
    if q in src:
        return True
    # Allow an ellipsis-joined quote if every part is present in order.
    parts = [p.strip() for p in re.split(r"\.\.\.|…", quote) if p.strip()]
    if len(parts) > 1:
        pos = 0
        for p in parts:
            i = src.find(norm(p).strip(" ."), pos)
            if i < 0:
                return False
            pos = i
        return True
    return False


def _tokens(s: str) -> set[str]:
    return {t for t in norm(s).split() if t not in _STOP and len(t) > 1}


def patient_fact_supported(fact: str, profile_text: str) -> bool:
    """A cited patient fact is supported if it appears in the profile, or (nearly) all of its content words do."""
    if not fact.strip():
        return False
    if norm(fact) in norm(profile_text):
        return True
    ft, pt = _tokens(fact), _tokens(profile_text)
    if not ft:
        return False
    return len(ft & pt) / len(ft) >= 0.8


@dataclass
class ValidationReport:
    checked: int = 0
    rejected: int = 0
    unsupported_patient_claims: int = 0
    invalid_trial_quotes: int = 0
    unknown_criterion_ids: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        return self.rejected / self.checked if self.checked else 0.0


def verify_nct(nct_id: str, trial: NormalizedTrial, retrieved_ids: set[str] | None = None) -> bool:
    if nct_id.strip().upper() != trial.nct_id:
        return False
    return retrieved_ids is None or trial.nct_id in retrieved_ids


def check_citations(text: str, valid_ids: set[str]) -> tuple[list[str], list[str]]:
    cited = CITATION_RE.findall(text or "")
    good = [c for c in cited if c in valid_ids]
    bad = [c for c in cited if c not in valid_ids]
    return good, bad


def strip_invalid_citations(text: str, valid_ids: set[str]) -> str:
    return CITATION_RE.sub(lambda m: m.group(0) if m.group(1) in valid_ids else "", text)
