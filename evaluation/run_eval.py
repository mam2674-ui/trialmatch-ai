"""TrialMatch AI evaluation.

Usage (from repo root, with the backend venv):
    backend/.venv/bin/python evaluation/run_eval.py --llm none        # deterministic rules only
    backend/.venv/bin/python evaluation/run_eval.py --llm claude      # rules + Claude (needs ANTHROPIC_API_KEY)
    backend/.venv/bin/python evaluation/run_eval.py --retrieval       # retrieval recall ablation (loads PubMedBERT)

Reports go to evaluation/results/. These are SYNTHETIC benchmark results on fictional cases written by the
author; they are not clinical validation.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
sys.path.insert(0, str(ROOT))

from app.schemas.patient import Biomarker, Conflict, Fact, LabValue, PatientProfile, Treatment  # noqa: E402
from app.schemas.trial import NormalizedTrial  # noqa: E402
from app.services.eligibility_engine import assess_trial  # noqa: E402
from app.services.trial_normalizer import normalize_study, split_criteria  # noqa: E402
from cases import CASES  # noqa: E402

RESULTS = ROOT / "results"


def build_patient(d: dict) -> PatientProfile:
    p = PatientProfile(is_demo=True)
    f = lambda v: Fact(value=v, source="patient_provided")  # noqa: E731
    if "age" in d:
        p.demographics.age_years = f(d["age"])
    if "sex" in d:
        p.demographics.sex = f(d["sex"])
    p.diagnosis.primary_condition = f(d["condition"])
    if "stage" in d:
        p.diagnosis.stage = f(d["stage"])
    if "metastatic" in d:
        p.diagnosis.metastatic = f(d["metastatic"])
    p.diagnosis.biomarkers = [Biomarker(name=n, status=s, detail=det) for n, s, det in d.get("markers", [])]
    p.history.prior_treatments = [Treatment(name=n, status="completed", progression=prog) for n, prog in d.get("tx", [])]
    p.history.current_medications = [f(m) for m in d.get("meds", [])]
    p.history.comorbidities = [f(c) for c in d.get("comorbid", [])]
    p.history.labs = [LabValue(name=n, value=v, unit=u) for n, v, u in d.get("labs", [])]
    if "ecog" in d:
        p.history.ecog_performance_status = f(d["ecog"])
    if "preg" in d:
        p.history.pregnant_or_breastfeeding = f(d["preg"])
    p.conflicts = [Conflict(field=a, description=b) for a, b in d.get("conflicts", [])]
    return p


def build_trial(case: dict) -> NormalizedTrial:
    t = case.get("trial", {})
    return NormalizedTrial(
        nct_id="NCT9" + str(abs(hash(case["id"])) % 10_000_000).zfill(7), brief_title=f"Fictional study: {case['id']}",
        overall_status=t.get("status", "RECRUITING"), sex=t.get("sex", "ALL"),
        min_age_years=t.get("min_age"), max_age_years=t.get("max_age"),
        minimum_age=f"{t['min_age']} Years" if "min_age" in t else None,
        maximum_age=f"{t['max_age']} Years" if "max_age" in t else None,
        criteria=split_criteria(case["text"]), conditions=[case["patient"]["condition"]],
    )


def tone(c) -> str:
    if c.is_blocker:
        return "blocker"
    if c.assessment == "NOT_APPLICABLE":
        return "na"
    if c.assessment == "UNKNOWN":
        return "unknown"
    return "ok"


async def run_eligibility(llm_name: str) -> dict:
    llm = None
    if llm_name == "claude":
        from app.services.llm import DisabledLLM, get_llm
        llm = get_llm()
        if isinstance(llm, DisabledLLM):
            raise SystemExit("ANTHROPIC_API_KEY is not set; cannot run --llm claude.")
    rows, crit_rows = [], []
    for case in CASES:
        p, t = build_patient(case["patient"]), build_trial(case)
        start = time.perf_counter()
        out = await assess_trial(p, t, llm)
        latency = time.perf_counter() - start
        got = {c.criterion_id: c for c in out["criteria"]}
        for cid, label in case["labels"].items():
            c = got.get(cid)
            crit_rows.append(dict(case=case["id"], criterion=cid, label=label, predicted=tone(c) if c else "missing",
                                  source=c.source if c else None))
        flagged = {c.criterion_id for c in out["criteria"] if c.is_blocker}
        text_ids = {c.criterion_id for c in t.criteria}
        labeled_text_ids = {k for k in case["labels"] if k[0] in "IEU" and k[1:].isdigit()}
        rep = out["report"]
        rows.append(dict(
            case=case["id"], tags=case["tags"], category=out["eligibility"].category, expected=case["expected"],
            category_ok=out["eligibility"].category in case["expected"], ai_status=out["ai_status"],
            known_blocker=case.get("known_blocker"), blocker_detected=case.get("known_blocker") in flagged if case.get("known_blocker") else None,
            flagged=sorted(flagged), split_ok=labeled_text_ids <= text_ids and len(text_ids) == len(labeled_text_ids),
            llm_checked=rep.checked, llm_rejected=rep.rejected, unsupported_claims=rep.unsupported_patient_claims,
            invalid_quotes=rep.invalid_trial_quotes, invented_ids=rep.unknown_criterion_ids,
            invalid_summary_citations=sum("non-existent criteria" in n for n in rep.notes),
            summary_citations=out["eligibility"].explanation.count("["),
            latency_s=round(latency, 3),
        ))
    return dict(rows=rows, criteria=crit_rows)


def summarize_eligibility(res: dict, llm_name: str, usage=None) -> dict:
    rows, crit = res["rows"], res["criteria"]
    decided = [c for c in crit if c["predicted"] in ("ok", "blocker", "na")]
    labeled_blockers = [c for c in crit if c["label"] == "blocker"]
    non_blockers = [c for c in crit if c["label"] != "blocker"]
    known = [r for r in rows if r["known_blocker"]]
    s = dict(
        mode=llm_name,
        cases=len(rows),
        labeled_criteria=len(crit),
        criterion_agreement=round(sum(c["label"] == c["predicted"] for c in crit) / len(crit), 3),
        decided_fraction=round(len(decided) / len(crit), 3),
        precision_when_decided=round(sum(c["label"] == c["predicted"] for c in decided) / len(decided), 3) if decided else None,
        blocker_recall_per_criterion=round(sum(c["predicted"] == "blocker" for c in labeled_blockers) / len(labeled_blockers), 3),
        false_blocker_rate=round(sum(c["predicted"] == "blocker" for c in non_blockers) / len(non_blockers), 3),
        known_exclusion_detection_rate=round(sum(r["blocker_detected"] for r in known) / len(known), 3),
        category_agreement=round(sum(r["category_ok"] for r in rows) / len(rows), 3),
        criterion_split_accuracy=round(sum(r["split_ok"] for r in rows) / len(rows), 3),
        latency_median_s=round(statistics.median(r["latency_s"] for r in rows), 3),
        latency_max_s=round(max(r["latency_s"] for r in rows), 3),
    )
    checked = sum(r["llm_checked"] for r in rows)
    if checked:
        s.update(
            llm_claims_checked=checked,
            unsupported_claim_rate=round(sum(r["unsupported_claims"] for r in rows) / checked, 4),
            invalid_quote_rate=round(sum(r["invalid_quotes"] for r in rows) / checked, 4),
            invented_criterion_ids=sum(r["invented_ids"] for r in rows),
            explanation_citation_validity=round(
                1 - sum(r["invalid_summary_citations"] for r in rows) / max(1, sum(r["summary_citations"] for r in rows)), 3),
            ai_ok_cases=sum(r["ai_status"] == "ok" for r in rows),
        )
    if usage is not None:
        s.update(llm_calls=usage.calls, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                 estimated_cost_usd=usage.cost_usd)
    return s


def real_record_split_stats() -> dict:
    with gzip.open(ROOT / "data" / "retrieval_pool.json.gz", "rt") as f:
        recs = json.load(f)["records"]
    n, both, crit = 0, 0, 0
    for r in recs:
        t = normalize_study(r["study"])
        kinds = Counter(c.kind for c in t.criteria)
        n += 1
        both += bool(kinds["inclusion"] and kinds["exclusion"])
        crit += len(t.criteria)
    return dict(records=n, with_inclusion_and_exclusion_sections=round(both / n, 3), mean_criteria_per_record=round(crit / n, 1))


# ---------------- retrieval ----------------

DEMO_TO_BUCKET = {"breast-her2": "breast_her2", "nsclc-egfr": "nsclc_egfr", "parkinsons": "parkinson",
                  "t2d-cvd": "t2d_cvd", "cystic-fibrosis": "cf"}


def run_retrieval(ks=(10, 25, 50)) -> dict:
    import numpy as np
    from app.core.config import get_settings
    from app.data.demo_profiles import DEMOS
    from app.services.embedding_service import EmbeddingModel, trial_sections
    from app.services.ranking_service import bm25_scores, query_terms, query_text, score_trial, trial_text

    with gzip.open(ROOT / "data" / "retrieval_pool.json.gz", "rt") as f:
        recs = json.load(f)["records"]
    seen, trials, bucket = set(), [], {}
    for r in recs:
        t = normalize_study(r["study"])
        if t.nct_id in seen:
            continue
        seen.add(t.nct_id)
        trials.append(t)
        bucket[t.nct_id] = r["bucket"]

    model = EmbeddingModel(get_settings().embedding_model)
    t0 = time.perf_counter()
    chunks, owners, sections = [], [], []
    for t in trials:
        for sec, cs in trial_sections(t).items():
            for c in cs:
                chunks.append(c)
                owners.append(t.nct_id)
                sections.append(sec)
    vecs = model.encode(chunks)
    embed_seconds = time.perf_counter() - t0

    out = {"pool_size": len(trials), "chunks_embedded": len(chunks), "embedding_seconds": round(embed_seconds, 1),
           "label_definition": "relevant = returned by ClinicalTrials.gov's own condition search for that disease", "profiles": {}}
    agg = {m: {k: [] for k in ks} for m in ("keyword", "semantic", "hybrid")}
    for demo in DEMOS:
        p = demo["profile"]
        rel = {n for n, b in bucket.items() if b == DEMO_TO_BUCKET[demo["id"]]}
        qv = model.encode([query_text(p)])[0]
        sims = vecs @ qv
        sem: dict[str, dict] = {}
        for nct, sec, sim in zip(owners, sections, sims):
            d = sem.setdefault(nct, {"best": float(sim), "best_section": sec})
            if sim > d["best"]:
                d.update(best=float(sim), best_section=sec)
        bm = bm25_scores(query_terms(p), {t.nct_id: trial_text(t) for t in trials})
        top = max(bm.values()) or 1
        kw = {k: v / top for k, v in bm.items()}
        rankings = {
            "keyword": sorted(trials, key=lambda t: -kw[t.nct_id]),
            "semantic": sorted(trials, key=lambda t: -sem[t.nct_id]["best"]),
            "hybrid": sorted(trials, key=lambda t: -score_trial(p, t, semantic=sem[t.nct_id], keyword=kw[t.nct_id], distance=None)[0].score),
        }
        prof = {}
        for m, ranked in rankings.items():
            prof[m] = {}
            for k in ks:
                hit = sum(1 for t in ranked[:k] if t.nct_id in rel)
                recall = hit / len(rel)
                prof[m][f"recall@{k}"] = round(recall, 3)
                agg[m][k].append(recall)
        out["profiles"][demo["id"]] = dict(relevant=len(rel), **prof)
    out["mean"] = {m: {f"recall@{k}": round(statistics.mean(v), 3) for k, v in d.items()} for m, d in agg.items()}
    return out


def write_report(elig: dict | None, summary: dict | None, retrieval: dict | None, split: dict | None, mode: str) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    if elig:
        (RESULTS / f"eligibility_{mode}.json").write_text(json.dumps({"summary": summary, "split_on_real_records": split, **elig}, indent=2))
    if retrieval:
        (RESULTS / "retrieval.json").write_text(json.dumps(retrieval, indent=2))
    lines = [f"# Evaluation report ({mode}, {stamp})", "",
             "Synthetic benchmark on fictional cases written by the author. Not clinical validation." if summary else
             "Retrieval ranking over real recorded ClinicalTrials.gov records. Not clinical validation.", ""]
    if summary:
        lines += ["## Eligibility", "", "| Metric | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in summary.items()]
        lines += ["", "### Per case", "", "| Case | Expected | Got | OK | Known blocker found |", "|---|---|---|---|---|"]
        for r in elig["rows"]:
            kb = "" if r["blocker_detected"] is None else ("yes" if r["blocker_detected"] else "**no**")
            lines.append(f"| {r['case']} | {'/'.join(r['expected'])} | {r['category']} | {'yes' if r['category_ok'] else '**no**'} | {kb} |")
        disagreements = [c for c in elig["criteria"] if c["label"] != c["predicted"]]
        lines += ["", f"### Criterion disagreements ({len(disagreements)})", "", "| Case | Criterion | Label | Predicted | Source |", "|---|---|---|---|---|"]
        lines += [f"| {c['case']} | {c['criterion']} | {c['label']} | {c['predicted']} | {c['source']} |" for c in disagreements]
    if split:
        lines += ["", "## Criteria splitting on real records", "", json.dumps(split)]
    if retrieval:
        lines += ["", "## Retrieval recall (real records)", "", retrieval["label_definition"] + ".",
                  f"Pool: {retrieval['pool_size']} real records; ~50 relevant per profile, so recall@10 and recall@25 "
                  "are capped at about 0.2 and 0.5. recall@50 equals R-precision and is the informative number.", "",
                  "| Method | " + " | ".join(retrieval["mean"]["hybrid"]) + " |", "|---|" + "---|" * len(retrieval["mean"]["hybrid"])]
        for m, d in retrieval["mean"].items():
            lines.append(f"| {m} | " + " | ".join(str(v) for v in d.values()) + " |")
    path = RESULTS / f"report_{mode}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["none", "claude"], default="none")
    ap.add_argument("--retrieval", action="store_true")
    args = ap.parse_args()
    elig = summary = retrieval = split = None
    mode = args.llm if not args.retrieval else "retrieval"
    if not args.retrieval:
        elig = asyncio.run(run_eligibility(args.llm))
        usage = None
        if args.llm == "claude":
            from app.services.llm import get_llm
            usage = get_llm().usage
        summary = summarize_eligibility(elig, args.llm, usage)
        split = real_record_split_stats()
        print(json.dumps(summary, indent=2))
        print(json.dumps(split))
    else:
        retrieval = run_retrieval()
        print(json.dumps(retrieval["mean"], indent=2))
    print("report:", write_report(elig, summary, retrieval, split, mode))


if __name__ == "__main__":
    main()
