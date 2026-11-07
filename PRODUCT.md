# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: patients and caregivers who have a diagnosis (often cancer, but also neurological, metabolic and rare
inherited conditions) and want to know whether any clinical trial could be open to them. They arrive with partial
knowledge: they may know the diagnosis and stage, sometimes biomarker results, rarely the details trials ask about
(progression dates, performance status, lab values). Many are reading while worried, tired, or between appointments,
and some are reading on behalf of someone else.

Secondary: clinicians, research coordinators and researchers who need the precise criteria and evidence; they are
served by the detailed clinical explanation mode and the full criterion-by-criterion breakdown, not by the
homepage's first impression.

## Product Purpose

Turn a plain-language description of a patient's situation into a structured, correctable profile; search live
ClinicalTrials.gov records; and show, study by study, which eligibility criteria appear met, which may block
participation, and what still needs confirming, each tied to the exact criterion text.

Success: a patient or caregiver leaves with a short, honest list of studies worth asking a doctor about, knows what
questions to bring, and is never told they are "eligible". Currently a portfolio-grade build that is intended to
grow into a real product after the necessary security, privacy, legal and compliance work.

## Positioning

Every assessment is traceable: to a verbatim criterion in the official record and to a fact the user actually
provided. Missing information stays "unknown" and is never counted as meeting a requirement. Final eligibility
always belongs to the study's research team.

## Operating Context

- Data comes live from the ClinicalTrials.gov API v2; each study links to its official listing.
- Users describe the situation in free text or a form, review and correct the extracted profile, then search.
- Results are preliminary screening in four categories: Potential match, Needs more information, Requires clinical
  review, Potentially ineligible.
- Follow-up yes/no questions refine the profile; studies can be compared (2–4) and saved locally.
- Sessions are anonymous and expire; descriptions are not stored.

## Capabilities and Constraints

- Never present a determination of eligibility, a probability of eligibility, or a claim that a treatment works or
  is better than another.
- No names, birthdates or identifying records are requested; users are told not to enter them.
- Works without the AI layer (rules and retrieved studies only) and must say so when that is the case.
- Does not claim HIPAA compliance.
- Undecided: hosting, real-user deployment, and any account system.

## Brand Commitments

None fixed. The name "TrialMatch AI", the headline and the visual identity are all open to change.

## Evidence on Hand

- Live ClinicalTrials.gov data and five fictional demo patients (backend/app/data/demo_profiles.py).
- Synthetic evaluation results in evaluation/results/ (27 fictional cases; retrieval over 299 real recorded
  records). These are not clinical validation and must never be presented as such.
- No users, testimonials, partner institutions, clinical endorsements or press exist; do not fabricate any.

## Product Principles

1. Honesty over reassurance: show uncertainty plainly rather than smoothing it into a confident answer.
2. Traceable or it doesn't ship: every claim points to a criterion and a user-provided fact.
3. Plain language first, precision one click away.
4. The patient's time and attention are scarce: lead with what to ask the care team next.
5. Privacy by default: collect only what screening needs, keep it briefly, never log it.

## Accessibility & Inclusion

Audience includes older adults, people under stress, and caregivers on phones. Target WCAG 2.1 AA: readable type
sizes, strong contrast, status never conveyed by color alone, full keyboard use, and respect for reduced motion.
