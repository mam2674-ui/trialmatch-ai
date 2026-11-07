import type { Fact, PatientProfile } from "./types";

const unknown = <T,>(): Fact<T> => ({ value: null, source: "unknown" });

export function emptyProfile(): PatientProfile {
  return {
    demographics: { age_years: unknown(), sex: unknown(), location: { source: "unknown" }, travel_radius_miles: unknown() },
    diagnosis: {
      primary_condition: unknown(), subtype: unknown(), stage: unknown(), diagnosis_date: unknown(), histology: unknown(),
      metastatic: unknown(), biomarkers: [], findings: [],
    },
    history: {
      prior_treatments: [], current_medications: [], comorbidities: [], ecog_performance_status: unknown(), labs: [],
      prior_trial_participation: unknown(), pregnant_or_breastfeeding: unknown(),
    },
    preferences: { willing_to_travel: null, treatment_interests: [], preferred_phases: [], recruiting_only: true, remote_ok: null },
    conflicts: [],
    is_demo: false,
  };
}

/** Drop blank rows the user added but never filled in, so they are not sent as facts. */
export function cleanProfile(p: PatientProfile): PatientProfile {
  const d = structuredClone(p);
  d.diagnosis.biomarkers = d.diagnosis.biomarkers.filter((b) => b.name.trim());
  d.history.prior_treatments = d.history.prior_treatments.filter((t) => t.name.trim());
  d.history.current_medications = d.history.current_medications.filter((f) => f.value);
  d.history.comorbidities = d.history.comorbidities.filter((f) => f.value);
  d.diagnosis.findings = d.diagnosis.findings.filter((f) => f.value);
  return d;
}

export function knownFactCount(p: PatientProfile) {
  const facts = [
    p.demographics.age_years, p.demographics.sex, p.demographics.travel_radius_miles, p.diagnosis.primary_condition,
    p.diagnosis.subtype, p.diagnosis.stage, p.diagnosis.histology, p.diagnosis.metastatic, p.history.ecog_performance_status,
  ];
  return facts.filter((f) => f.value !== null).length + p.diagnosis.biomarkers.length + p.history.prior_treatments.length;
}
