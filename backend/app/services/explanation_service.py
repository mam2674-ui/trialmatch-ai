"""'Explain This Trial': three grounded sections in patient-friendly or clinical language.

Claude receives only the trial record, the criterion assessments already validated for this session, and
the verified profile. Its output is validated (cited criteria must exist; NCT must match). The glossary
comes from a curated static list, not from the model. Without Claude, a rule-based explanation is built
from the study record verbatim plus the validated assessments.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.schemas.match import CriterionResult, ExplainResponse, ExplanationSection
from app.schemas.patient import PatientProfile
from app.schemas.trial import NormalizedTrial
from app.services import evidence_validator as ev
from app.services.llm import UNTRUSTED_DATA_POLICY, LLMClient, LLMError
from app.services.terminology import glossary_terms_in


class LLMExplanation(BaseModel):
    nct_id: str
    what_is_tested: str = Field(description="What the study is testing and its objective")
    why_might_fit: str = Field(description="Which profile characteristics correspond with requirements; cite [ids]")
    what_to_check: str = Field(description="Unresolved criteria, records needed; cite [ids]")
    questions_for_team: list[str] = Field(description="3-6 questions the patient could ask the research team")


def _system(mode: str) -> str:
    style = ("Write for a patient or caregiver at roughly an 8th-grade reading level. Explain medical terms in "
             "plain words, but keep every clinically important qualification." if mode == "patient" else
             "Write for a clinician: concise, precise clinical terminology, reference criteria explicitly.")
    return f"""You explain one clinical trial to a person considering it, based only on the provided study \
record and the provided criterion assessments. {style}

Rules:
- Use only information in <trial_record>, <assessments> and <patient_profile>. Do not add requirements, \
outcomes, dosing or facts that are not there.
- Cite criteria ids in square brackets, e.g. [I2] or [E5], whenever you refer to a requirement.
- Never say the person is eligible, will be accepted, or that the treatment will work or is better than \
another option. Participation is never guaranteed; final eligibility is decided by the study team.
- If something is unknown, say it needs to be checked.

{UNTRUSTED_DATA_POLICY}"""


def _record(t: NormalizedTrial) -> str:
    inter = "\n".join(f"- {i.type or ''} {i.name}: {i.description or ''}" for i in t.interventions)
    return (f"<trial_record nct_id=\"{t.nct_id}\">\nTitle: {t.brief_title}\nOfficial title: {t.official_title}\n"
            f"Phase: {', '.join(t.phases)}\nConditions: {', '.join(t.conditions)}\nSummary: {t.brief_summary}\n"
            f"Interventions:\n{inter}\n</trial_record>")


def _assessments(criteria: list[CriterionResult]) -> str:
    return "\n".join(f"[{c.criterion_id}] ({c.kind}) {c.assessment}: {c.criterion_text[:400]} — {c.explanation}"
                     for c in criteria if c.kind != "structured" or c.assessment != "NOT_APPLICABLE")


def _first_sentences(text: str | None, n: int = 3) -> str:
    if not text:
        return ""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sents[:n])


def rule_explanation(t: NormalizedTrial, criteria: list[CriterionResult], mode: str) -> ExplainResponse:
    inter = ", ".join(i.name for i in t.interventions) or "not listed"
    tested = (f"From the study record: \"{_first_sentences(t.brief_summary)}\" "
              f"Interventions listed: {inter}. Phase: {', '.join(t.phases) or 'not specified'}.")
    met = [c for c in criteria if c.assessment == "MET" and not c.is_blocker and c.kind != "structured"]
    blockers = [c for c in criteria if c.is_blocker]
    unknown = [c for c in criteria if c.assessment == "UNKNOWN" and c.kind != "structured"]
    fit = (" ".join(f"{c.explanation} [{c.criterion_id}]" for c in met[:5]) or
           "No individual criteria have been confirmed against your profile yet.")
    check_parts = []
    if blockers:
        check_parts.append("Possible blockers: " + " ".join(f"{c.explanation} [{c.criterion_id}]" for c in blockers[:4]))
    if unknown:
        check_parts.append("Still to confirm: " + " ".join(f"[{c.criterion_id}]" for c in unknown[:10]) + ".")
    check_parts.append("The research team will review your medical records to make the final decision.")
    qs = ["Am I likely to meet the eligibility requirements, and what tests would be needed to confirm?",
          "What does participation involve (visits, procedures, time commitment)?",
          "Which study site is closest to me, and is it currently enrolling?"]
    qs += [c.question for c in unknown if c.question][:3]
    return ExplainResponse(
        nct_id=t.nct_id, mode=mode, source="rules",
        sections=[
            ExplanationSection(heading="What is this study testing?", body=tested),
            ExplanationSection(heading="Why might this trial fit?", body=fit, cited_criteria=[c.criterion_id for c in met[:5]]),
            ExplanationSection(heading="What still needs to be checked?", body=" ".join(check_parts),
                               cited_criteria=[c.criterion_id for c in (blockers + unknown)[:10]]),
        ],
        questions_for_team=qs, glossary=glossary_terms_in(" ".join([t.brief_summary or "", t.brief_title, inter])),
    )


async def explain_trial(t: NormalizedTrial, criteria: list[CriterionResult], profile: PatientProfile | None,
                        mode: str, llm: LLMClient) -> ExplainResponse:
    user = (f"{_record(t)}\n<assessments>\n{_assessments(criteria)}\n</assessments>\n"
            f"<patient_profile>\n{profile.known_facts_text() if profile else '(not provided)'}\n</patient_profile>\n\n"
            f"Explain trial {t.nct_id} in {mode} mode.")
    try:
        out = await llm.structured(system=_system(mode), user=user, output=LLMExplanation, max_tokens=6000)
    except LLMError:
        return rule_explanation(t, criteria, mode)
    notes: list[str] = []
    if not ev.verify_nct(out.nct_id, t):
        return rule_explanation(t, criteria, mode).model_copy(
            update={"validation_notes": ["AI explanation referred to a different study and was discarded."]})
    valid = {c.criterion_id for c in t.criteria} | {"AGE", "SEX", "STATUS"}
    sections = []
    for heading, body in (("What is this study testing?", out.what_is_tested),
                          ("Why might this trial fit?", out.why_might_fit),
                          ("What still needs to be checked?", out.what_to_check)):
        good, bad = ev.check_citations(body, valid)
        if bad:
            notes.append(f"Removed citations to non-existent criteria: {bad}")
            body = ev.strip_invalid_citations(body, valid)
        sections.append(ExplanationSection(heading=heading, body=body, cited_criteria=sorted(set(good))))
    # The two eligibility sections must be grounded in at least one real criterion.
    if not sections[1].cited_criteria and not sections[2].cited_criteria:
        fallback = rule_explanation(t, criteria, mode)
        fallback.validation_notes = ["AI explanation did not cite any trial criteria and was replaced."]
        return fallback
    if re.search(r"\byou (are|would be) (eligible|accepted|approved)\b|\bwill (work|cure)\b", " ".join(s.body for s in sections), re.I):
        fallback = rule_explanation(t, criteria, mode)
        fallback.validation_notes = ["AI explanation contained an overconfident claim and was replaced."]
        return fallback
    text = " ".join([t.brief_summary or "", t.brief_title] + [s.body for s in sections])
    return ExplainResponse(nct_id=t.nct_id, mode=mode, sections=sections,
                           questions_for_team=out.questions_for_team[:6], glossary=glossary_terms_in(text),
                           source="claude", validation_notes=notes)
