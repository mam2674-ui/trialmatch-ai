// Types mirroring the FastAPI response models (backend/app/schemas). Keep in sync.

export type Source = "patient_provided" | "model_extracted" | "rule_extracted" | "unknown";

export interface Fact<T> {
  value: T | null;
  source: Source;
  evidence?: string | null;
}

export interface Location {
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  source: Source;
  evidence?: string | null;
  lat?: number | null;
  lon?: number | null;
  geocoded_label?: string | null;
}

export type BiomarkerStatus =
  | "positive" | "negative" | "mutated" | "wild_type" | "amplified" | "not_detected" | "other";

export interface Biomarker {
  name: string;
  status: BiomarkerStatus;
  detail?: string | null;
  source: Source;
  evidence?: string | null;
}

export interface Treatment {
  name: string;
  category?: string | null;
  status: "completed" | "ongoing" | "planned" | "unknown";
  progression: "yes" | "no" | "unknown";
  source: Source;
  evidence?: string | null;
}

export interface LabValue {
  name: string;
  value: number;
  unit: string;
  measured_on?: string | null;
  source: Source;
  evidence?: string | null;
}

export interface PatientProfile {
  demographics: {
    age_years: Fact<number>;
    sex: Fact<"female" | "male">;
    location: Location;
    travel_radius_miles: Fact<number>;
  };
  diagnosis: {
    primary_condition: Fact<string>;
    subtype: Fact<string>;
    stage: Fact<string>;
    diagnosis_date: Fact<string>;
    histology: Fact<string>;
    metastatic: Fact<boolean>;
    biomarkers: Biomarker[];
    findings: Fact<string>[];
  };
  history: {
    prior_treatments: Treatment[];
    current_medications: Fact<string>[];
    comorbidities: Fact<string>[];
    ecog_performance_status: Fact<number>;
    labs: LabValue[];
    prior_trial_participation: Fact<boolean>;
    pregnant_or_breastfeeding: Fact<boolean>;
  };
  preferences: {
    willing_to_travel: boolean | null;
    treatment_interests: string[];
    preferred_phases: string[];
    recruiting_only: boolean;
    remote_ok: boolean | null;
  };
  conflicts: { field: string; description: string }[];
  is_demo: boolean;
}

export interface ParseResponse {
  profile: PatientProfile;
  extraction_method: "claude" | "rules";
  warnings: string[];
  dropped_unverified: string[];
}

export interface Contact {
  name?: string | null;
  role?: string | null;
  phone?: string | null;
  phone_ext?: string | null;
  email?: string | null;
}

export interface TrialSite {
  facility?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  country?: string | null;
  status?: string | null;
  lat?: number | null;
  lon?: number | null;
  contacts: Contact[];
  distance_miles?: number | null;
}

export interface Criterion {
  criterion_id: string;
  kind: "inclusion" | "exclusion" | "unclassified";
  text: string;
}

export interface Trial {
  nct_id: string;
  brief_title: string;
  official_title?: string | null;
  overall_status?: string | null;
  study_type?: string | null;
  phases: string[];
  conditions: string[];
  keywords: string[];
  brief_summary?: string | null;
  detailed_description?: string | null;
  interventions: { type?: string | null; name: string; description?: string | null; other_names: string[] }[];
  sponsor?: string | null;
  eligibility_text?: string | null;
  criteria: Criterion[];
  sex?: string | null;
  minimum_age?: string | null;
  maximum_age?: string | null;
  healthy_volunteers?: boolean | null;
  enrollment_count?: number | null;
  enrollment_type?: string | null;
  central_contacts: Contact[];
  locations: TrialSite[];
  last_update_post_date?: string | null;
  status_verified_date?: string | null;
  fetched_at?: string | null;
  url: string;
}

export type Assessment = "MET" | "NOT_MET" | "UNKNOWN" | "NOT_APPLICABLE";
export type Category =
  | "POTENTIAL_MATCH" | "NEEDS_MORE_INFORMATION" | "POTENTIALLY_INELIGIBLE" | "REQUIRES_CLINICAL_REVIEW";

export interface CriterionResult {
  criterion_id: string;
  kind: "inclusion" | "exclusion" | "unclassified" | "structured";
  criterion_text: string;
  assessment: Assessment;
  is_blocker: boolean;
  patient_evidence: string[];
  trial_evidence?: string | null;
  explanation: string;
  needs_info: boolean;
  unknown_reason?: string | null;
  impact: "high" | "routine";
  question?: string | null;
  source: "rule" | "claude" | "not_assessed";
  validation_notes: string[];
}

export interface RelevanceComponent {
  name: string;
  score: number | null;
  weight: number;
  detail: string;
}

export interface MatchResult {
  rank: number;
  trial: Trial;
  relevance: {
    score: number;
    components: RelevanceComponent[];
    note: string;
    penalty_factor: number;
    penalty_reason?: string | null;
  };
  why_retrieved: string[];
  eligibility: {
    category: Category;
    label: string;
    headline: string;
    explanation: string;
    explanation_source: "claude" | "rules";
    blockers: string[];
    met: string[];
    unknown: string[];
    review: string[];
  };
  criteria: CriterionResult[];
  completeness: {
    total_criteria: number;
    assessed: number;
    unknown: number;
    not_assessed: number;
    fraction_assessed: number;
  };
  questions: string[];
  nearest_site?: TrialSite | null;
  distance_miles?: number | null;
  sites_within_radius?: number | null;
  ai_status: "ok" | "unavailable" | "validation_failed" | "not_run" | "error";
  ai_note?: string | null;
}

export interface FollowUpQuestion {
  id: string;
  question: string;
  why: string;
  options: { label: string; value: "yes" | "no" | "not_sure" }[];
  patch: Record<string, unknown> & { type: string };
  affected_trials: string[];
  priority: number;
}

export interface MatchResponse {
  session_id: string;
  expires_at: string;
  results: MatchResult[];
  questions: FollowUpQuestion[];
  stats: {
    candidates_retrieved: number;
    total_available: number | null;
    studies_analyzed: number;
    ai_analyzed: number;
    potential_matches: number;
    unresolved: number;
    conflicts: number;
    ineligible: number;
  };
  data: {
    source: "live" | "cache";
    refreshed_at: string | null;
    api_data_timestamp: string | null;
    queries: string[];
  };
  profile_used: PatientProfile;
  warnings: string[];
  ai_enabled: boolean;
  disclaimer: string;
}

export interface ExplainResponse {
  nct_id: string;
  mode: "patient" | "clinical";
  sections: { heading: string; body: string; cited_criteria: string[] }[];
  questions_for_team: string[];
  glossary: Record<string, string>;
  source: "claude" | "rules";
  validation_notes: string[];
  disclaimer: string;
}

export interface CompareResponse {
  nct_ids: string[];
  rows: { field: string; values: Record<string, string | string[] | null> }[];
  note: string;
}

export interface DemoProfile {
  id: string;
  title: string;
  challenge: string;
  narrative: string;
  profile: PatientProfile;
}

export interface Health {
  status: string;
  database: string;
  pgvector: string;
  clinicaltrials_gov: string;
  clinicaltrials_gov_data_timestamp: string | null;
  ai: string;
  ai_model: string | null;
  embeddings: string;
  embedding_model: string | null;
}

export interface MethodologyStats {
  cached_trials: number;
  embedded_chunks: number;
  live_refreshes: number;
  failed_refreshes: number;
  last_successful_refresh: string | null;
  clinicaltrials_gov_data_timestamp: string | null;
  active_sessions: number;
  session_ttl_minutes: number;
  trial_cache_ttl_hours: number;
  search_cache_ttl_hours: number;
  relevance_weights: Record<string, number>;
  ai_model: string | null;
  embedding_model: string | null;
  usage: { llm_calls: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number };
}
