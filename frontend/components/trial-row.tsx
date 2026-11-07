"use client";

import Link from "next/link";
import { Bookmark, BookmarkCheck, ExternalLink, MapPin } from "lucide-react";
import { useAppState } from "@/components/app-state";
import { CitedText, Ledger } from "@/components/ledger";
import { CATEGORY_STYLE, CategoryBadge, RecruitStatus } from "@/components/status";
import type { MatchResult } from "@/lib/types";
import { cn, formatDate, formatPhases, siteLabel } from "@/lib/utils";

export function TrialRow({ r }: { r: MatchResult }) {
  const { compare, toggleCompare, toggleSaved, isSaved } = useAppState();
  const t = r.trial;
  const style = CATEGORY_STYLE[r.eligibility.category];
  const inCompare = compare.includes(t.nct_id);
  const saved = isSaved(t.nct_id);

  return (
    <article className="relative grid gap-4 border-b border-rule py-6 pl-5 md:grid-cols-[1fr_15rem] md:gap-8" aria-labelledby={`t-${t.nct_id}`}>
      <span aria-hidden="true" className={cn("absolute bottom-6 left-0 top-6 w-1 rounded-full", style.bar)} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <CategoryBadge category={r.eligibility.category} />
          <span className="text-sm text-ink-soft">{r.eligibility.headline}</span>
        </div>
        <h2 id={`t-${t.nct_id}`} className="mt-2 text-xl leading-snug">
          <Link href={`/trials/${t.nct_id}`} className="text-ink hover:text-link hover:underline">{t.brief_title}</Link>
        </h2>
        <p className="tabular mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-soft">
          <span className="font-medium text-ink">{t.nct_id}</span>
          <span>{formatPhases(t.phases)}</span>
          <RecruitStatus status={t.overall_status} />
          {t.sponsor && <span>{t.sponsor}</span>}
        </p>

        {r.why_retrieved.length > 0 && (
          <p className="mt-3 text-sm text-ink-soft">
            <span className="font-medium text-ink">Why it was retrieved: </span>
            {r.why_retrieved.join("; ")}.
          </p>
        )}

        <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink">
          <CitedText text={r.eligibility.explanation} criteria={r.criteria} />
        </p>
        {r.ai_note && <p className="mt-2 text-xs text-ink-soft">{r.ai_note}</p>}

        <div className="mt-4">
          <Ledger criteria={r.criteria} limit={3} compact />
        </div>
      </div>

      <aside className="grid content-start gap-3 text-sm md:border-l md:border-rule md:pl-6">
        <div>
          <p className="text-ink-soft">Search relevance</p>
          <p className="tabular font-serif text-2xl text-ink">{Math.round(r.relevance.score)}<span className="text-sm text-ink-soft"> / 100</span></p>
          <p className="text-xs leading-snug text-ink-soft">Topic match only, not a chance of eligibility.</p>
        </div>
        <div>
          <p className="text-ink-soft">Nearest site</p>
          {r.nearest_site ? (
            <p className="flex gap-1 text-ink">
              <MapPin className="mt-0.5 size-3.5 shrink-0 text-teal" aria-hidden="true" />
              <span>
                {siteLabel({ city: r.nearest_site.city, state: r.nearest_site.state })}
                {r.distance_miles != null && <span className="tabular text-ink-soft"> · about {Math.round(r.distance_miles)} mi</span>}
                {r.nearest_site.status && r.nearest_site.status !== t.overall_status && (
                  <span className="block text-xs text-amber">Site status: {r.nearest_site.status.replace(/_/g, " ").toLowerCase()}</span>
                )}
              </span>
            </p>
          ) : (
            <p className="text-ink-soft">{t.locations.length ? `${t.locations.length} site(s); distance unavailable` : "No sites listed"}</p>
          )}
          {r.sites_within_radius != null && (
            <p className="tabular text-xs text-ink-soft">{r.sites_within_radius} site(s) within your travel distance</p>
          )}
        </div>
        <p className="text-xs text-ink-soft">Record updated {formatDate(t.last_update_post_date)}</p>
        <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1">
          <label className="flex items-center gap-1.5 text-ink">
            <input type="checkbox" aria-label={`Compare ${t.nct_id}`} className="size-4 accent-[#13294B]" checked={inCompare}
              disabled={!inCompare && compare.length >= 4} onChange={() => toggleCompare(t.nct_id)} />
            Compare
          </label>
          <button onClick={() => toggleSaved(t.nct_id, t.brief_title)} className="flex items-center gap-1 text-ink hover:text-link"
            aria-pressed={saved}>
            {saved ? <BookmarkCheck className="size-4 text-teal" aria-hidden="true" /> : <Bookmark className="size-4" aria-hidden="true" />}
            {saved ? "Saved" : "Save"}
          </button>
        </div>
        <div className="grid gap-1.5">
          <Link href={`/trials/${t.nct_id}`} className="font-medium text-link underline">Full criteria breakdown</Link>
          <a href={t.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-link underline">
            Official listing on ClinicalTrials.gov <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
        </div>
      </aside>
    </article>
  );
}
