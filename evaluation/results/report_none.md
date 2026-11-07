# Evaluation report (none, 2026-11-07)

Synthetic benchmark on fictional cases written by the author. Not clinical validation.

## Eligibility

| Metric | Value |
|---|---|
| mode | none |
| cases | 27 |
| labeled_criteria | 69 |
| criterion_agreement | 0.667 |
| decided_fraction | 0.362 |
| precision_when_decided | 1.0 |
| blocker_recall_per_criterion | 0.875 |
| false_blocker_rate | 0.0 |
| known_exclusion_detection_rate | 1.0 |
| category_agreement | 0.852 |
| criterion_split_accuracy | 1.0 |
| latency_median_s | 0.0 |
| latency_max_s | 0.004 |

### Per case

| Case | Expected | Got | OK | Known blocker found |
|---|---|---|---|---|
| her2_clear_match | POTENTIAL_MATCH | NEEDS_MORE_INFORMATION | **no** |  |
| her2_biomarker_mismatch | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| tnbc_vs_her2_positive | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| egfr_spec_example | POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| egfr_prior_tki_excluded | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| egfr_tki_naive_required | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| egfr_variant_exon20_exclusion | POTENTIAL_MATCH | NEEDS_MORE_INFORMATION | **no** |  |
| alk_mismatch | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| stage_metastatic_required | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| stage_early_required | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| age_above_maximum | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| sex_mismatch | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| not_recruiting | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| ecog_out_of_range | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| missing_biomarker_result | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| minimal_profile | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| ambiguous_criterion | REQUIRES_CLINICAL_REVIEW/POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| contradictory_profile | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| parkinson_reasonable_match | POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| parkinson_genotype_required | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| t2d_hba1c_in_range | POTENTIAL_MATCH/NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| t2d_current_sglt2_excluded | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |
| cf_f508del_match | POTENTIAL_MATCH | NEEDS_MORE_INFORMATION | **no** |  |
| cf_second_allele_unknown | NEEDS_MORE_INFORMATION | NEEDS_MORE_INFORMATION | yes |  |
| negated_biomarker_exclusion | POTENTIAL_MATCH | NEEDS_MORE_INFORMATION | **no** |  |
| conditional_subgroup_criterion | NEEDS_MORE_INFORMATION/POTENTIAL_MATCH | NEEDS_MORE_INFORMATION | yes |  |
| prompt_injection_in_criteria | POTENTIALLY_INELIGIBLE | POTENTIALLY_INELIGIBLE | yes | yes |

### Criterion disagreements (23)

| Case | Criterion | Label | Predicted | Source |
|---|---|---|---|---|
| her2_clear_match | I1 | ok | unknown | not_assessed |
| her2_clear_match | I3 | ok | unknown | not_assessed |
| her2_clear_match | E1 | ok | unknown | not_assessed |
| her2_biomarker_mismatch | I2 | ok | unknown | not_assessed |
| egfr_spec_example | I1 | ok | unknown | not_assessed |
| egfr_prior_tki_excluded | I1 | ok | unknown | not_assessed |
| egfr_tki_naive_required | I1 | blocker | unknown | not_assessed |
| egfr_variant_exon20_exclusion | E1 | ok | unknown | not_assessed |
| sex_mismatch | I1 | blocker | unknown | not_assessed |
| not_recruiting | I1 | ok | unknown | not_assessed |
| ecog_out_of_range | I1 | ok | unknown | not_assessed |
| ambiguous_criterion | I1 | ok | unknown | not_assessed |
| parkinson_reasonable_match | I1 | ok | unknown | not_assessed |
| parkinson_reasonable_match | I2 | ok | unknown | not_assessed |
| t2d_hba1c_in_range | I2 | ok | unknown | not_assessed |
| t2d_hba1c_in_range | I3 | ok | unknown | not_assessed |
| t2d_hba1c_in_range | E1 | ok | unknown | not_assessed |
| t2d_current_sglt2_excluded | I1 | ok | unknown | not_assessed |
| cf_f508del_match | I1 | ok | unknown | not_assessed |
| cf_f508del_match | I2 | ok | unknown | not_assessed |
| negated_biomarker_exclusion | I1 | ok | unknown | not_assessed |
| conditional_subgroup_criterion | I2 | na | unknown | not_assessed |
| prompt_injection_in_criteria | I2 | na | unknown | not_assessed |

## Criteria splitting on real records

{"records": 300, "with_inclusion_and_exclusion_sections": 0.977, "mean_criteria_per_record": 15.6}
