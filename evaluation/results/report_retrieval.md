# Evaluation report (retrieval, 2026-11-07)

Retrieval ranking over real recorded ClinicalTrials.gov records. Not clinical validation.


## Retrieval recall (real records)

relevant = returned by ClinicalTrials.gov's own condition search for that disease.
Pool: 299 real records; ~50 relevant per profile, so recall@10 and recall@25 are capped at about 0.2 and 0.5. recall@50 equals R-precision and is the informative number.

| Method | recall@10 | recall@25 | recall@50 |
|---|---|---|---|
| keyword | 0.197 | 0.498 | 0.944 |
| semantic | 0.201 | 0.49 | 0.868 |
| hybrid | 0.201 | 0.502 | 0.928 |
