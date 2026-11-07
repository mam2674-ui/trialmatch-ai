"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Database, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { useAppState } from "@/components/app-state";
import { FollowUps } from "@/components/followups";
import { TrialRow } from "@/components/trial-row";
import { CATEGORY_STYLE } from "@/components/status";
import { api } from "@/lib/api";
import type { Category, MatchResult } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

type Sort = "relevance" | "status" | "distance" | "updated";
const STATUS_ORDER: Record<string, number> = { RECRUITING: 0, NOT_YET_RECRUITING: 1, ENROLLING_BY_INVITATION: 2, ACTIVE_NOT_RECRUITING: 3 };
const CATS: Category[] = ["POTENTIAL_MATCH", "REQUIRES_CLINICAL_REVIEW", "NEEDS_MORE_INFORMATION", "POTENTIALLY_INELIGIBLE"];

function sortResults(rs: MatchResult[], sort: Sort) {
  const blocked = (r: MatchResult) => (r.eligibility.category === "POTENTIALLY_INELIGIBLE" ? 1 : 0);
  const by: Record<Sort, (a: MatchResult, b: MatchResult) => number> = {
    // Studies with identified blockers always sit below the rest when sorting by relevance.
    relevance: (a, b) => blocked(a) - blocked(b) || b.relevance.score - a.relevance.score,
    status: (a, b) => (STATUS_ORDER[a.trial.overall_status ?? ""] ?? 9) - (STATUS_ORDER[b.trial.overall_status ?? ""] ?? 9) || b.relevance.score - a.relevance.score,
    distance: (a, b) => (a.distance_miles ?? Infinity) - (b.distance_miles ?? Infinity),
    updated: (a, b) => (b.trial.last_update_post_date ?? "").localeCompare(a.trial.last_update_post_date ?? ""),
  };
  return [...rs].sort(by[sort]);
}

export function ResultsView() {
  const router = useRouter();
  const { match, hydrated, clearAll, compare } = useAppState();
  const [sort, setSort] = useState<Sort>("relevance");
  const [cats, setCats] = useState<Set<Category>>(new Set(CATS));
  const [phase, setPhase] = useState("any");

  const visible = useMemo(() => {
    if (!match) return [];
    return sortResults(
      match.results.filter((r) => cats.has(r.eligibility.category) && (phase === "any" || r.trial.phases.includes(phase))),
      sort,
    );
  }, [match, cats, phase, sort]);

  if (!hydrated) return <p className="text-ink-soft">Loading…</p>;
  if (!match) {
    return (
      <div className="rounded-md border border-dashed border-rule p-10 text-center">
        <p className="text-lg text-ink">No search yet.</p>
        <p className="mt-1 text-ink-soft">Describe the medical situation to see matching studies.</p>
        <Link href="/intake" className={cn(buttonVariants(), "mt-5 h-10 px-4")}>Start a profile</Link>
      </div>
    );
  }

  const expired = new Date(match.expires_at) < new Date();
  const s = match.stats;
  const phases = Array.from(new Set(match.results.flatMap((r) => r.trial.phases))).sort();
  const counts = Object.fromEntries(CATS.map((c) => [c, match.results.filter((r) => r.eligibility.category === c).length]));

  async function deleteData() {
    if (!match) return;
    await api.deleteSession(match.session_id).catch(() => undefined);
    clearAll();
    router.push("/");
  }

  return (
    <div className="grid gap-8">
      <header className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl text-ink">Potentially relevant studies</h1>
            <p className="mt-1 text-ink-soft">
              For {match.profile_used.diagnosis.primary_condition.value}
              {match.profile_used.is_demo && " (fictional demo patient)"}. Preliminary screening only; the research team decides eligibility.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/intake" className={buttonVariants({ variant: "outline" })}>Edit profile</Link>
            {compare.length >= 2 && <Link href="/compare" className={buttonVariants()}>Compare {compare.length} studies</Link>}
          </div>
        </div>

        <dl className="tabular grid grid-cols-2 gap-px overflow-hidden rounded-md border border-rule bg-rule text-sm sm:grid-cols-3 lg:grid-cols-6">
          {[
            ["Candidates retrieved", s.candidates_retrieved, s.total_available != null ? `of ${s.total_available} in registry` : ""],
            ["Studies analyzed", s.studies_analyzed, `${s.ai_analyzed} with AI criteria review`],
            ["Potential matches", s.potential_matches, "no blockers found"],
            ["Unresolved", s.unresolved, "need info or review"],
            ["Eligibility conflicts", s.conflicts, "possible blockers"],
            ["Data", match.data.source === "live" ? "Live" : "Cached", formatDateTime(match.data.refreshed_at)],
          ].map(([k, v, sub]) => (
            <div key={k as string} className="bg-white px-4 py-3">
              <dt className="text-ink-soft">{k}</dt>
              <dd className="font-serif text-2xl text-ink">{v}</dd>
              <dd className="text-xs text-ink-soft">{sub}</dd>
            </div>
          ))}
        </dl>

        {match.warnings.map((w) => (
          <p key={w} className="flex gap-2 rounded bg-amber-wash p-3 text-sm text-amber">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> {w}
          </p>
        ))}
        {expired && (
          <p className="rounded bg-mist p-3 text-sm text-ink-soft">
            This session&apos;s server-side data has expired and been deleted. Results remain visible in this tab; run the search
            again to analyze more studies or open detailed breakdowns.
          </p>
        )}
      </header>

      <FollowUps questions={match.questions} />

      <div className="grid gap-8 lg:grid-cols-[14rem_1fr]">
        <aside aria-label="Filter and sort" className="grid content-start gap-6 text-sm lg:sticky lg:top-6 lg:self-start">
          <div>
            <label htmlFor="sort" className="font-medium text-ink">Sort by</label>
            <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)}
              className="mt-1 h-9 w-full rounded-md border border-input bg-white px-2">
              <option value="relevance">Search relevance</option>
              <option value="status">Recruitment status</option>
              <option value="distance">Distance</option>
              <option value="updated">Last updated</option>
            </select>
          </div>
          <fieldset>
            <legend className="font-medium text-ink">Assessment</legend>
            <div className="mt-2 grid gap-1.5">
              {CATS.map((c) => (
                <label key={c} className="flex items-center gap-2">
                  <input type="checkbox" aria-label={`Show ${CATEGORY_STYLE[c].label}`} className="size-4 accent-[#13294B]" checked={cats.has(c)}
                    onChange={() => setCats((prev) => { const n = new Set(prev); if (n.has(c)) n.delete(c); else n.add(c); return n; })} />
                  <span className={CATEGORY_STYLE[c].text}>{CATEGORY_STYLE[c].label}</span>
                  <span className="tabular ml-auto text-ink-soft">{counts[c]}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div>
            <label htmlFor="phase" className="font-medium text-ink">Phase</label>
            <select id="phase" value={phase} onChange={(e) => setPhase(e.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-input bg-white px-2">
              <option value="any">Any phase</option>
              {phases.map((p) => <option key={p} value={p}>{p.replace("PHASE", "Phase ").replace("EARLY_", "Early ")}</option>)}
            </select>
          </div>
          <div className="border-t border-rule pt-4 text-xs leading-relaxed text-ink-soft">
            <p className="flex gap-1.5"><Database className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              ClinicalTrials.gov data as of {formatDateTime(match.data.api_data_timestamp)}.</p>
            <p className="mt-2">Searches run: {match.data.queries.join("; ")}</p>
            <p className="mt-2">Session data on our server expires {formatDateTime(match.expires_at)}.</p>
            <Button variant="ghost" size="sm" className="mt-2 -ml-2 text-brick" onClick={deleteData}>
              <Trash2 aria-hidden="true" /> Delete my data now
            </Button>
          </div>
        </aside>

        <section aria-label="Results">
          <p className="tabular text-sm text-ink-soft" aria-live="polite">Showing {visible.length} of {match.results.length} studies</p>
          {visible.length === 0 ? (
            <p className="mt-6 text-ink-soft">No studies match these filters. Select more assessment categories or another phase.</p>
          ) : (
            <div className="border-t border-rule">{visible.map((r) => <TrialRow key={r.trial.nct_id} r={r} />)}</div>
          )}
          <p className="mt-6 max-w-prose text-xs leading-relaxed text-ink-soft">{match.disclaimer}</p>
        </section>
      </div>
    </div>
  );
}
