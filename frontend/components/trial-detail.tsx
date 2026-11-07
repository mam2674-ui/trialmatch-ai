"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Bookmark, BookmarkCheck, ExternalLink, Loader2, Mail, Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppState } from "@/components/app-state";
import { CitedText, Ledger } from "@/components/ledger";
import { ExplainPanel } from "@/components/explain-panel";
import { AssessmentLabel, CATEGORY_STYLE, CategoryBadge, RecruitStatus } from "@/components/status";
import { api, ApiError } from "@/lib/api";
import type { Contact, CriterionResult, MatchResult, Trial } from "@/lib/types";
import { cn, formatDate, formatDateTime, formatPhases, siteLabel } from "@/lib/utils";

const SOURCE_TEXT = { rule: "Deterministic rule", claude: "Claude, verified", not_assessed: "Not analyzed" } as const;

export function TrialDetail({ nctId }: { nctId: string }) {
  const { match, setMatch, profile, hydrated, toggleSaved, isSaved } = useAppState();
  const fromSession = match?.results.find((r) => r.trial.nct_id === nctId) ?? null;
  const [trial, setTrial] = useState<Trial | null>(fromSession?.trial ?? null);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [assessing, setAssessing] = useState(false);

  useEffect(() => {
    if (!hydrated) return;
    api.trial(nctId)
      .then((d) => { setTrial(d.trial); setSource(d.data_source); })
      .catch((e) => { if (!fromSession) setError(e instanceof ApiError ? e.message : "Could not load this study."); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, nctId]);

  async function assess() {
    if (!match || !profile) return;
    setAssessing(true);
    setError(null);
    try {
      const r = await api.assess(nctId, match.session_id, profile);
      setMatch({ ...match, results: match.results.map((x) => (x.trial.nct_id === nctId ? r : x)) });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Analysis failed.");
    } finally {
      setAssessing(false);
    }
  }

  if (error && !trial) {
    return (
      <div role="alert" className="rounded border border-brick/30 bg-brick-wash p-5 text-brick">
        <p className="font-medium">{error}</p>
        <Link href="/results" className="mt-2 inline-block underline">Back to results</Link>
      </div>
    );
  }
  if (!trial) return <p className="flex items-center gap-2 text-ink-soft"><Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading study record…</p>;

  const r: MatchResult | null = fromSession;
  const saved = isSaved(trial.nct_id);

  return (
    <div className="grid gap-10">
      <header>
        <Link href={r ? "/results" : "/saved"} className="inline-flex items-center gap-1 text-sm text-link hover:underline">
          <ArrowLeft className="size-3.5" aria-hidden="true" /> {r ? "Back to results" : "Back"}
        </Link>
        <h1 className="mt-3 max-w-4xl text-3xl leading-tight text-ink">{trial.brief_title}</h1>
        {trial.official_title && trial.official_title !== trial.brief_title && (
          <p className="mt-2 max-w-4xl text-ink-soft">{trial.official_title}</p>
        )}
        <p className="tabular mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-ink-soft">
          <span className="font-medium text-ink">{trial.nct_id}</span>
          <span>{formatPhases(trial.phases)}</span>
          <RecruitStatus status={trial.overall_status} />
          <span>{trial.study_type?.toLowerCase()}</span>
          {trial.sponsor && <span>Sponsor: {trial.sponsor}</span>}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <a href={trial.url} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-ink px-3 py-2 text-sm font-medium text-white hover:bg-ink/90">
            Official listing on ClinicalTrials.gov <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
          <Button variant="outline" onClick={() => toggleSaved(trial.nct_id, trial.brief_title)} aria-pressed={saved}>
            {saved ? <BookmarkCheck className="text-teal" aria-hidden="true" /> : <Bookmark aria-hidden="true" />} {saved ? "Saved" : "Save study"}
          </Button>
          <span className="text-xs text-ink-soft">
            Record last updated {formatDate(trial.last_update_post_date)} · retrieved {formatDateTime(trial.fetched_at)}
            {source && ` (${source === "live" ? "live" : "cached"})`}
          </span>
        </div>
      </header>

      {r ? (
        <section aria-labelledby="assess-h" className={cn("rounded-md border p-5", "border-rule bg-white")}>
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="assess-h" className="text-xl text-ink">Preliminary eligibility</h2>
            <CategoryBadge category={r.eligibility.category} />
          </div>
          <p className="mt-1 text-sm text-ink-soft">{CATEGORY_STYLE[r.eligibility.category].blurb} {r.eligibility.headline}.</p>
          <p className="mt-4 max-w-prose leading-relaxed text-ink"><CitedText text={r.eligibility.explanation} criteria={r.criteria} /></p>
          <p className="tabular mt-3 text-xs text-ink-soft">
            {r.completeness.assessed} of {r.completeness.total_criteria} criteria assessed · {r.completeness.unknown} unknown ·{" "}
            {r.completeness.not_assessed} not analyzed · explanation by {r.eligibility.explanation_source === "claude" ? "Claude (validated)" : "rules"}
          </p>
          {r.ai_note && <p className="mt-2 text-sm text-amber">{r.ai_note}</p>}
          {r.ai_status !== "ok" && match?.ai_enabled && r.eligibility.category !== "POTENTIALLY_INELIGIBLE" && (
            <Button className="mt-3" onClick={assess} disabled={assessing}>
              {assessing && <Loader2 className="animate-spin" aria-hidden="true" />} Analyze criteria with Claude
            </Button>
          )}
          {error && <p role="alert" className="mt-2 text-sm text-brick">{error}</p>}
          <div className="mt-6 border-t border-rule pt-5"><Ledger criteria={r.criteria} limit={8} /></div>
        </section>
      ) : (
        <p className="rounded bg-mist p-4 text-sm text-ink-soft">
          This study isn&apos;t part of your current search, so no eligibility assessment is shown. Run a search from your
          profile to see how its criteria compare.
        </p>
      )}

      <ExplainPanel nctId={trial.nct_id} sessionId={r ? match?.session_id : undefined} profile={profile ?? undefined} criteria={r?.criteria ?? []} />

      <div className="grid gap-10 lg:grid-cols-[1fr_20rem]">
        <section aria-labelledby="crit-h" className="min-w-0">
          <h2 id="crit-h" className="text-2xl text-ink">Inclusion and exclusion criteria</h2>
          <p className="mt-1 text-sm text-ink-soft">
            Criterion text is copied verbatim from the study record. For exclusions, &ldquo;present&rdquo; means the exclusion
            appears to apply and could prevent participation.
          </p>
          {r ? <CriteriaList criteria={r.criteria} /> : <PlainCriteria trial={trial} />}
          <details className="mt-6 rounded border border-rule bg-white p-4">
            <summary className="cursor-pointer text-sm font-medium text-ink">Original eligibility text from ClinicalTrials.gov</summary>
            <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink-soft">{trial.eligibility_text ?? "Not provided."}</pre>
          </details>
        </section>

        <aside className="grid content-start gap-8 text-sm">
          <StudyFacts trial={trial} />
          <Contacts title="Study contacts" contacts={trial.central_contacts} />
          <Sites trial={trial} nearestNote={r?.distance_miles != null} />
        </aside>
      </div>

      {trial.brief_summary && (
        <section className="max-w-prose">
          <h2 className="text-2xl text-ink">Study summary</h2>
          <p className="mt-3 whitespace-pre-line leading-relaxed text-ink">{trial.brief_summary}</p>
          {trial.interventions.length > 0 && (
            <>
              <h3 className="mt-6 text-lg text-ink">Interventions</h3>
              <ul className="mt-2 grid gap-2">
                {trial.interventions.map((i) => (
                  <li key={i.name}>
                    <span className="font-medium text-ink">{i.name}</span>
                    <span className="text-ink-soft"> ({i.type?.toLowerCase() ?? "type not listed"})</span>
                    {i.description && <p className="text-sm text-ink-soft">{i.description}</p>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
    </div>
  );
}

function CriteriaList({ criteria }: { criteria: CriterionResult[] }) {
  const groups = [
    { title: "Structured requirements", items: criteria.filter((c) => c.kind === "structured") },
    { title: "Inclusion criteria", items: criteria.filter((c) => c.kind === "inclusion" || c.kind === "unclassified") },
    { title: "Exclusion criteria", items: criteria.filter((c) => c.kind === "exclusion") },
  ];
  return (
    <div className="mt-6 grid gap-8">
      {groups.filter((g) => g.items.length).map((g) => (
        <div key={g.title}>
          <h3 className="text-lg text-ink">{g.title}</h3>
          <ol className="mt-2 divide-y divide-rule border-y border-rule">
            {g.items.map((c) => (
              <li key={c.criterion_id} id={`crit-${c.criterion_id}`} className="grid scroll-mt-6 gap-2 py-4 sm:grid-cols-[3.5rem_1fr]">
                <span className="tabular font-serif text-ink-soft">{c.criterion_id}</span>
                <div className="min-w-0">
                  <p className="whitespace-pre-line text-sm leading-relaxed text-ink">{c.criterion_text}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <AssessmentLabel c={c} />
                    <span className="text-xs text-ink-soft">{SOURCE_TEXT[c.source]}</span>
                    {c.impact === "high" && c.assessment === "UNKNOWN" && <span className="text-xs text-amber">key requirement</span>}
                  </div>
                  {c.source !== "not_assessed" && <p className="mt-1 text-sm text-ink-soft">{c.explanation}</p>}
                  {(c.patient_evidence.length > 0 || c.trial_evidence) && (
                    <dl className="mt-2 grid gap-1 text-xs">
                      {c.patient_evidence.length > 0 && (
                        <div className="flex gap-1.5"><dt className="text-ink-soft">From your profile:</dt><dd className="text-ink">{c.patient_evidence.join("; ")}</dd></div>
                      )}
                      {c.trial_evidence && (
                        <div className="flex gap-1.5"><dt className="shrink-0 text-ink-soft">From the record:</dt><dd className="text-ink">&ldquo;{c.trial_evidence}&rdquo;</dd></div>
                      )}
                    </dl>
                  )}
                  {c.question && <p className="mt-2 text-sm text-amber">Ask: {c.question}</p>}
                  {c.validation_notes.length > 0 && (
                    <details className="mt-2 text-xs text-ink-soft">
                      <summary className="cursor-pointer">Validation notes ({c.validation_notes.length})</summary>
                      <ul className="mt-1 list-disc pl-4">{c.validation_notes.map((n) => <li key={n}>{n}</li>)}</ul>
                    </details>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}

function PlainCriteria({ trial }: { trial: Trial }) {
  return (
    <ol className="mt-4 divide-y divide-rule border-y border-rule">
      {trial.criteria.map((c) => (
        <li key={c.criterion_id} className="grid gap-2 py-3 sm:grid-cols-[3.5rem_1fr]">
          <span className="font-serif text-ink-soft">{c.criterion_id}</span>
          <p className="whitespace-pre-line text-sm text-ink">{c.text}</p>
        </li>
      ))}
    </ol>
  );
}

function StudyFacts({ trial }: { trial: Trial }) {
  const rows: [string, string][] = [
    ["Conditions", trial.conditions.join(", ") || "Not listed"],
    ["Ages", `${trial.minimum_age ?? "No minimum"} to ${trial.maximum_age ?? "no maximum"}`],
    ["Sex", trial.sex ? trial.sex.toLowerCase() : "Not specified"],
    ["Healthy volunteers", trial.healthy_volunteers == null ? "Not specified" : trial.healthy_volunteers ? "Accepted" : "Not accepted"],
    ["Enrollment", trial.enrollment_count ? `${trial.enrollment_count} (${trial.enrollment_type?.toLowerCase() ?? ""})` : "Not listed"],
  ];
  return (
    <div>
      <h2 className="text-lg text-ink">Study facts</h2>
      <dl className="mt-2 grid gap-2">
        {rows.map(([k, v]) => <div key={k}><dt className="text-ink-soft">{k}</dt><dd className="text-ink">{v}</dd></div>)}
      </dl>
    </div>
  );
}

function Contacts({ title, contacts }: { title: string; contacts: Contact[] }) {
  return (
    <div>
      <h2 className="text-lg text-ink">{title}</h2>
      {contacts.length === 0 ? (
        <p className="mt-2 text-ink-soft">No central contact listed. Check site contacts below or the official listing.</p>
      ) : (
        <ul className="mt-2 grid gap-3">
          {contacts.map((c, i) => (
            <li key={i}>
              <p className="text-ink">{c.name ?? "Contact"}</p>
              {c.phone && <p className="flex items-center gap-1 text-ink-soft"><Phone className="size-3.5" aria-hidden="true" />{c.phone}{c.phone_ext && ` ext. ${c.phone_ext}`}</p>}
              {c.email && <a className="flex items-center gap-1 break-all text-link underline" href={`mailto:${c.email}`}><Mail className="size-3.5 shrink-0" aria-hidden="true" />{c.email}</a>}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-ink-soft">Contact details are shown exactly as listed on ClinicalTrials.gov.</p>
    </div>
  );
}

function Sites({ trial, nearestNote }: { trial: Trial; nearestNote: boolean }) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? trial.locations : trial.locations.slice(0, 8);
  return (
    <div>
      <h2 className="text-lg text-ink">Study sites <span className="tabular text-sm font-normal text-ink-soft">({trial.locations.length})</span></h2>
      <p className="mt-1 text-xs text-ink-soft">
        Each site has its own recruitment status, which can differ from the study&apos;s overall status.
        {nearestNote && " Distances use city-level coordinates published by ClinicalTrials.gov, so they are approximate."}
      </p>
      <ul className="mt-3 grid gap-2.5">
        {shown.map((s, i) => (
          <li key={i}>
            <p className="text-ink">{siteLabel(s)}</p>
            <p className="text-xs text-ink-soft">{s.status ? s.status.replace(/_/g, " ").toLowerCase() : "site status not listed"}</p>
          </li>
        ))}
      </ul>
      {trial.locations.length > 8 && (
        <button className="mt-2 text-link underline" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show fewer" : `Show all ${trial.locations.length} sites`}
        </button>
      )}
    </div>
  );
}
