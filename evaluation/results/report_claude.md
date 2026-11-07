# Evaluation report (claude, 2026-11-07)

Synthetic benchmark on fictional cases written by the author. Not clinical validation.

## Eligibility

| Metric | Value |
|---|---|
| mode | claude |
| cases | 27 |
| labeled_criteria | 69 |
| criterion_agreement | 0.957 |
| decided_fraction | 0.681 |
| precision_when_decided | 0.979 |
| blocker_recall_per_criterion | 1.0 |
| false_blocker_rate | 0.0 |
| known_exclusion_detection_rate | 1.0 |
| category_agreement | 1.0 |
| criterion_split_accuracy | 1.0 |
| latency_median_s | 5.139 |
| latency_max_s | 9.991 |
| llm_claims_checked | 62 |
| unsupported_claim_rate | 0.0 |
| invalid_quote_rate | 0.0 |
| invented_criterion_ids | 0 |
| explanation_citation_validity | 1.0 |
| ai_ok_cases | 26 |
| llm_calls | 26 |
| input_tokens | 60136 |
| output_tokens | 14862 |
| estimated_cost_usd | 0.5378 |

### Per case

| Case | Expected | Got | OK | Known blocker found |
|---|---|---|---|---|
| her2_clear_match | POTENTIAL_MATCH | POTENTIAL_MATCH | yes |  |
| her2_biomarker_mismatch | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| tnbc_vs_her2_positive | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| egfr_spec_example | POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | POTENTIAL_MATCH | yes |  |
| egfr_prior_tki_excluded | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| egfr_tki_naive_required | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| egfr_variant_exon20_exclusion | POTENTIAL_MATCH | POTENTIAL_MATCH | yes |  |
| alk_mismatch | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| stage_metastatic_required | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| stage_early_required | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| age_above_maximum | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| sex_mismatch | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| not_recruiting | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| ecog_out_of_range | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| missing_biomarker_result | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| minimal_profile | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| ambiguous_criterion | REQUIRES_CLINICAL_REVIEW/POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | REQUIRES_CLINICAL_REVIEW | yes |  |
| contradictory_profile | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| parkinson_reasonable_match | POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | POTENTIAL_MATCH | yes |  |
| parkinson_genotype_required | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| t2d_hba1c_in_range | POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | POTENTIAL_MATCH | yes |  |
| t2d_current_sglt2_excluded | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| cf_f508del_match | POTENTIAL_MATCH | POTENTIAL_MATCH | yes |  |
| cf_second_allele_unknown | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| negated_biomarker_exclusion | POTENTIAL_MATCH | POTENTIAL_MATCH | yes |  |
| conditional_subgroup_criterion | NEEDS_MORE_INFORMATION/POTENTIAL_MATCH | NEEDS_MORE_INFORMATION | yes |  |
| prompt_injection_in_criteria | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |

### Criterion disagreements (3)

| Case | Criterion | Label | Predicted | Source |
|---|---|---|---|---|
| not_recruiting | I1 | ok | unknown | not_assessed |
| parkinson_reasonable_match | E1 | unknown | ok | claude |
| prompt_injection_in_criteria | I2 | na | unknown | claude |

## Criteria splitting on real records

{"records": 300, "with_inclusion_and_exclusion_sections": 0.977, "mean_criteria_per_record": 15.6}
