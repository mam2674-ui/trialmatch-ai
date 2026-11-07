"""Hybrid eligibility engine: deterministic rules + Claude criterion analysis + evidence validation.

Pipeline for one trial:
  1. Structured checks (age, sex, recruitment status) and definitive text rules (eligibility_rules).
  2. Claude assesses every criterion (MET / NOT_MET / UNKNOWN / NOT_APPLICABLE) with evidence.
  3. evidence_validator verifies each claim; unverifiable claims are downgraded to UNKNOWN.
     If too many claims fail, retry once with feedback; if it still fails -> ai_status=validation_failed.
  4. Merge: definitive rule results override the model. Criteria the model skipped stay "not assessed".
  5. Categorize with an explicit, explainable decision procedure (see `categorize`).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.match import (
    CATEGORY_LABELS, AIStatus, Completeness, CriterionResult, EligibilitySummary, UnknownReason,
)
from app.schemas.patient import PatientProfile
from app.schemas.trial import NormalizedTrial
from app.services import evidence_validator as ev
from app.services.eligibility_rules import criterion_rules, structured_checks
from app.services.llm import UNTRUSTED_DATA_POLICY, LLMClient, LLMError, LLMUnavailable

MAX_REJECTION_RATE = 0.3


class LLMCriterion(BaseModel):
    criterion_id: str
    assessment: Literal["MET", "NOT_MET", "UNKNOWN", "NOT_APPLICABLE"]
    trial_evidence: str = Field(description="Verbatim excerpt of the criterion text that the assessment relies on")
    patient_evidence: list[str] = Field(description="Facts copied from the <patient_profile> lines. Empty if none apply.")
    explanation: str = Field(description="One or two plain-English sentences")
    unknown_reason: UnknownReason | None = None
    impact: Literal["high", "routine"]
    question: str | None = Field(None, description="For missing_patient_info: one short yes/no question to ask the patient")


class LLMTrialAssessment(BaseModel):
    nct_id: str
    criteria: list[LLMCriterion]
    profile_conflicts: list[str] = Field(description="Contradictions in the profile relevant to this trial")
    summary: str = Field(description="3-5 plain-English sentences citing criteria ids in brackets, e.g. [I2]")


ASSESSOR_SYSTEM = f"""You are a careful clinical research coordinator doing a PRELIMINARY screen of one patient \
profile against one clinical trial's eligibility criteria. You never make final eligibility determinations.

For EVERY criterion listed in <criteria>, return one assessment using its exact criterion_id:
- Inclusion criteria: MET = the profile shows the requirement is satisfied; NOT_MET = the profile shows it is not \
satisfied; UNKNOWN = the profile does not say; NOT_APPLICABLE = the criterion does not apply to this patient \
(e.g. it concerns another cohort, sex, or disease).
- Exclusion criteria: MET means the exclusion condition IS PRESENT (a potential blocker). NOT_MET means the \
profile shows it is absent. UNKNOWN if the profile does not say.

Strict rules:
- Use only facts in <patient_profile>. Missing information is UNKNOWN, never MET. Do not infer test results, \
disease progression, dates, or treatment response that are not stated. Prior treatment with a drug does NOT \
establish progression on it.
- A multi-part criterion is MET only if every part is supported. If any required part is unknown, the \
criterion is UNKNOWN.
- trial_evidence must be copied verbatim from that criterion's text. patient_evidence items must be copied \
from the profile lines (may be shortened, never reworded or extended).
- For UNKNOWN choose unknown_reason: missing_patient_info (the patient could answer it), \
requires_screening_test (labs, scans, organ function checked at screening), ambiguous_criterion (the wording \
is unclear), requires_clinical_judgment (needs a clinician's interpretation).
- impact = "high" if the criterion concerns the diagnosis, disease subtype, stage/extent, biomarkers, prior \
therapies, or disease status (e.g. progression); "routine" for consent, labs, organ function, contraception, \
general health, logistics.
- For missing_patient_info with high impact, write one short, plain-language question that can be answered Yes, No, or Not sure (never "when", "which", "how many" or either/or questions).
- Never claim a treatment will work, never recommend one treatment over another, and never state the patient \
is eligible or approved.
- The summary must cite criteria ids in square brackets and should say what still needs confirmation.

{UNTRUSTED_DATA_POLICY}"""


def _trial_prompt(p: PatientProfile, t: NormalizedTrial) -> str:
    crit = "\n".join(f'<criterion id="{c.criterion_id}" kind="{c.kind}">{c.text}</criterion>' for c in t.criteria)
    return (
        f"<trial_record nct_id=\"{t.nct_id}\">\nTitle: {t.brief_title}\nConditions: {', '.join(t.conditions)}\n"
        f"Phase: {', '.join(t.phases) or 'not specified'}\n"
        f"Interventions: {'; '.join(i.name for i in t.interventions)}\n"
        f"Sex: {t.sex}; Age: {t.minimum_age or 'no minimum'} to {t.maximum_age or 'no maximum'}\n</trial_record>\n"
        f"<criteria>\n{crit}\n</criteria>\n\n"
        f"<patient_profile>\n{p.known_facts_text() or '(no clinical facts provided)'}\n</patient_profile>\n\n"
        f"Assess every criterion for trial {t.nct_id}."
    )


def validate_llm_assessment(out: LLMTrialAssessment, p: PatientProfile, t: NormalizedTrial,
                            retrieved: set[str] | None = None) -> tuple[dict[str, CriterionResult], ev.ValidationReport, str | None]:
    report = ev.ValidationReport()
    if not ev.verify_nct(out.nct_id, t, retrieved):
        report.notes.append(f"Model answered for {out.nct_id!r}, not {t.nct_id}; whole response rejected.")
        report.checked = report.rejected = max(len(out.criteria), 1)
        return {}, report, None
    by_id = {c.criterion_id: c for c in t.criteria}
    profile_text = p.known_facts_text()
    results: dict[str, CriterionResult] = {}
    for a in out.criteria:
        report.checked += 1
        src = by_id.get(a.criterion_id)
        if src is None:
            report.rejected += 1
            report.unknown_criterion_ids += 1
            report.notes.append(f"Model cited non-existent criterion {a.criterion_id!r}; dropped.")
            continue
        notes: list[str] = []
        assessment = a.assessment
        if a.trial_evidence and not ev.quote_in(a.trial_evidence, src.text):
            report.invalid_trial_quotes += 1
            notes.append("Model's quote of the criterion did not match the source text; quote removed.")
            trial_evidence = None
        else:
            trial_evidence = a.trial_evidence or None
        verified_patient = [f for f in a.patient_evidence if ev.patient_fact_supported(f, profile_text)]
        unsupported = [f for f in a.patient_evidence if f not in verified_patient]
        if unsupported:
            report.unsupported_patient_claims += len(unsupported)
            notes.append(f"Removed patient facts not found in the profile: {unsupported}")
        if assessment in ("MET", "NOT_MET") and not verified_patient:
            notes.append(f"Model said {assessment} without verifiable patient evidence; downgraded to UNKNOWN.")
            assessment = "UNKNOWN"
        if unsupported or (a.trial_evidence and trial_evidence is None) or assessment != a.assessment:
            report.rejected += 1
        reason = a.unknown_reason if assessment == "UNKNOWN" else None
        if assessment == "UNKNOWN" and reason is None:
            reason = "missing_patient_info"
        is_blocker = (src.kind != "exclusion" and assessment == "NOT_MET") or (src.kind == "exclusion" and assessment == "MET")
        question = a.question if assessment == "UNKNOWN" and reason == "missing_patient_info" else None
        results[src.criterion_id] = CriterionResult(
            criterion_id=src.criterion_id, kind=src.kind, criterion_text=src.text, assessment=assessment,
            is_blocker=is_blocker, patient_evidence=verified_patient, trial_evidence=trial_evidence,
            explanation=a.explanation, needs_info=assessment == "UNKNOWN" and reason == "missing_patient_info",
            unknown_reason=reason, impact=a.impact, question=question, source="claude", validation_notes=notes,
        )
    valid_ids = set(by_id) | {"AGE", "SEX", "STATUS"}
    _, bad = ev.check_citations(out.summary, valid_ids)
    summary = ev.strip_invalid_citations(out.summary, valid_ids) if bad else out.summary
    if bad:
        report.notes.append(f"Summary cited non-existent criteria {bad}; citations removed.")
    good, _ = ev.check_citations(summary, valid_ids)
    if not good:
        report.notes.append("Summary cited no criteria; replaced with a rule-generated summary.")
        summary = None
    return results, report, summary


def _not_assessed(t: NormalizedTrial, cid: str, why: str) -> CriterionResult:
    c = next(c for c in t.criteria if c.criterion_id == cid)
    return CriterionResult(criterion_id=c.criterion_id, kind=c.kind, criterion_text=c.text, assessment="UNKNOWN",
                           is_blocker=False, explanation=why, source="not_assessed", impact="routine")


def categorize(results: list[CriterionResult], ai_status: AIStatus, has_conflicts: bool) -> tuple[str, str]:
    """Explicit decision procedure. Returns (category, headline).

    1. Any blocker (inclusion NOT_MET / exclusion MET)            -> POTENTIALLY_INELIGIBLE
    2. Criteria text not analyzed (AI unavailable / not run)      -> NEEDS_MORE_INFORMATION
    3. No high-impact inclusion criterion confirmed, or most high-impact inclusion criteria are unknown
                                                                  -> NEEDS_MORE_INFORMATION
    4. Profile has conflicting information                        -> NEEDS_MORE_INFORMATION
    5. A high-impact criterion needs clinical interpretation      -> REQUIRES_CLINICAL_REVIEW
    6. Otherwise                                                  -> POTENTIAL_MATCH (confirmation still required)
    """
    blockers = [r for r in results if r.is_blocker]
    if blockers:
        return "POTENTIALLY_INELIGIBLE", f"{len(blockers)} potential blocker{'s' if len(blockers) > 1 else ''} identified"
    text_crit = [r for r in results if r.kind != "structured"]
    if ai_status != "ok" and text_crit:
        return "NEEDS_MORE_INFORMATION", "Automated checks found no blockers; detailed criteria not yet analyzed"
    high = [r for r in results if r.impact == "high" and r.assessment != "NOT_APPLICABLE" and r.kind != "structured"]
    high_unknown = [r for r in high if r.assessment == "UNKNOWN"]
    high_incl = [r for r in high if r.kind in ("inclusion", "unclassified")]
    incl_known = [r for r in high_incl if r.assessment in ("MET", "NOT_MET")]
    incl_unknown = [r for r in high_incl if r.assessment == "UNKNOWN"]
    if high_incl and (not incl_known or len(incl_unknown) > len(high_incl) / 2):
        return "NEEDS_MORE_INFORMATION", "Key requirements cannot be checked with the information provided"
    if has_conflicts:
        return "NEEDS_MORE_INFORMATION", "The profile contains conflicting information that must be resolved first"
    if any(r.unknown_reason in ("ambiguous_criterion", "requires_clinical_judgment") for r in high_unknown):
        return "REQUIRES_CLINICAL_REVIEW", "Some key criteria need a clinician's interpretation"
    if high_unknown:
        return "POTENTIAL_MATCH", "No blockers identified — some key requirements still need confirmation"
    return "POTENTIAL_MATCH", "No blockers identified — final eligibility must be confirmed by the study team"


def rule_summary(results: list[CriterionResult], category: str) -> str:
    blockers = [r for r in results if r.is_blocker]
    met = [r for r in results if r.assessment == "MET" and not r.is_blocker and r.kind != "structured"]
    unknown = [r for r in results if r.assessment == "UNKNOWN" and r.impact == "high"]
    parts = []
    if blockers:
        parts.append("Potential blockers: " + " ".join(f"{r.explanation} [{r.criterion_id}]" for r in blockers[:3]))
    if met:
        parts.append("Requirements that appear consistent with the profile: "
                     + ", ".join(f"[{r.criterion_id}]" for r in met[:6]) + ".")
    if unknown:
        parts.append("Still to confirm: " + ", ".join(f"[{r.criterion_id}]" for r in unknown[:6]) + ".")
    if not parts:
        parts.append("Automated checks of age, sex and recruitment status found no blockers. The detailed "
                     "inclusion and exclusion criteria have not been analyzed and must be reviewed.")
    return " ".join(parts)


async def assess_trial(p: PatientProfile, t: NormalizedTrial, llm: LLMClient | None, *,
                       retrieved: set[str] | None = None) -> dict:
    """Returns dict(criteria, eligibility, completeness, ai_status, ai_note, report)."""
    structured = structured_checks(p, t)
    rule_out = criterion_rules(p, t)
    llm_results: dict[str, CriterionResult] = {}
    llm_summary: str | None = None
    ai_status: AIStatus = "not_run"
    ai_note: str | None = None
    report = ev.ValidationReport()
    status_blocked = any(r.criterion_id == "STATUS" and r.is_blocker for r in structured)

    if llm is not None and t.criteria and not status_blocked:
        prompt = _trial_prompt(p, t)
        for attempt in range(2):
            try:
                out = await llm.structured(system=ASSESSOR_SYSTEM, user=prompt, output=LLMTrialAssessment, max_tokens=16000)
            except LLMUnavailable as exc:
                ai_status, ai_note = "unavailable", str(exc)
                break
            except LLMError as exc:
                ai_status, ai_note = "error", str(exc)
                break
            llm_results, report, llm_summary = validate_llm_assessment(out, p, t, retrieved)
            # Individually rejected claims are already downgraded; withhold everything only if failures are widespread.
            if report.rejected <= max(1, MAX_REJECTION_RATE * report.checked) and llm_results:
                ai_status = "ok"
                break
            ai_status = "validation_failed"
            ai_note = (f"{report.rejected} of {report.checked} AI criterion assessments failed evidence checks"
                       f"{' after a retry' if attempt else ''}. AI assessments were withheld for this study.")
            prompt += ("\n\nYour previous answer failed validation: " + "; ".join(report.notes[:5])
                       + ". Quote only verbatim text, cite only facts in the profile, and use UNKNOWN when unsure.")
        if ai_status != "ok":
            llm_results, llm_summary = {}, None
    elif status_blocked:
        ai_note = "The study is not currently enrolling, so detailed criteria were not analyzed."

    merged: list[CriterionResult] = list(structured)
    for c in t.criteria:
        rule = rule_out.get(c.criterion_id)
        model = llm_results.get(c.criterion_id)
        if rule and rule.definitive:
            r = rule.result
            if model and model.assessment != r.assessment and model.assessment != "UNKNOWN":
                r = r.model_copy(update={"validation_notes": r.validation_notes + [
                    f"Claude assessed this as {model.assessment}; the deterministic rule takes precedence."]})
            merged.append(r)
        elif model:
            merged.append(model)
        else:
            merged.append(_not_assessed(t, c.criterion_id, "Not analyzed: AI criterion analysis was not run for this "
                                        "study. Review this criterion with the study team."))

    category, headline = categorize(merged, ai_status, bool(p.conflicts))
    explanation = llm_summary if (ai_status == "ok" and llm_summary) else rule_summary(merged, category)
    total = len(t.criteria)
    unknown = sum(1 for r in merged if r.kind != "structured" and r.assessment == "UNKNOWN" and r.source != "not_assessed")
    not_assessed = sum(1 for r in merged if r.source == "not_assessed")
    eligibility = EligibilitySummary(
        category=category, label=CATEGORY_LABELS[category], headline=headline, explanation=explanation,
        explanation_source="claude" if (ai_status == "ok" and llm_summary) else "rules",
        blockers=[r.criterion_id for r in merged if r.is_blocker],
        met=[r.criterion_id for r in merged if r.assessment == "MET" and not r.is_blocker],
        unknown=[r.criterion_id for r in merged if r.assessment == "UNKNOWN"],
        review=[r.criterion_id for r in merged if r.unknown_reason in ("ambiguous_criterion", "requires_clinical_judgment")],
    )
    completeness = Completeness(
        total_criteria=total, assessed=total - unknown - not_assessed, unknown=unknown, not_assessed=not_assessed,
        fraction_assessed=round((total - unknown - not_assessed) / total, 3) if total else 0.0,
    )
    return dict(criteria=merged, eligibility=eligibility, completeness=completeness, ai_status=ai_status,
                ai_note=ai_note, report=report)


def debug_dump(result: dict) -> str:  # pragma: no cover - developer aid
    return json.dumps({k: (v.model_dump() if hasattr(v, "model_dump") else str(v)) for k, v in result.items()},
                      indent=2, default=str)
