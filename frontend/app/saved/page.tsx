"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { useAppState } from "@/components/app-state";
import { formatDate } from "@/lib/utils";

export default function SavedPage() {
  const { saved, toggleSaved, hydrated } = useAppState();
  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl text-ink">Saved studies</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Saved on this device only. We keep just the study number and title here, never your medical details.
      </p>
      {hydrated && saved.length === 0 ? (
        <p className="mt-8 rounded-md border border-dashed border-rule p-8 text-ink-soft">
          No saved studies yet. Use Save on any result to keep it here.
        </p>
      ) : (
        <ul className="mt-8 divide-y divide-rule border-y border-rule">
          {saved.map((s) => (
            <li key={s.nct_id} className="flex flex-wrap items-start justify-between gap-3 py-4">
              <div>
                <Link href={`/trials/${s.nct_id}`} className="font-serif text-lg font-semibold text-ink hover:underline">{s.title}</Link>
                <p className="tabular text-sm text-ink-soft">{s.nct_id} · saved {formatDate(s.saved_at)}</p>
              </div>
              <div className="flex gap-4 text-sm">
                <a href={`https://clinicaltrials.gov/study/${s.nct_id}`} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 text-link underline">
                  Official listing <ExternalLink className="size-3.5" aria-hidden="true" />
                </a>
                <button className="text-brick underline" onClick={() => toggleSaved(s.nct_id, s.title)}>Remove</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
